"""
Webhook handler — HMAC-SHA256 verified, deduplicated, with monetary validation.

Design:
- HMAC-SHA256 signature verification is a HARD GATE — reject before trusting.
- Use raw body for verification (not parsed JSON).
- Dedup via x-razorpay-event-id in webhook_events table.
- Events may arrive out of order — handle gracefully via state machine.
- Monetary consistency: webhook amount/currency must match local record.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Optional

from src.config import get_settings
from src.database import get_db, get_db_transaction

logger = logging.getLogger(__name__)

# ── Payment State Machine ─────────────────────────────────────────────────────
# Legal state transitions: current_state -> set of allowed next states
LEGAL_TRANSITIONS: dict[str, set[str]] = {
    "PENDING":      {"CREATED", "FAILED", "RECONCILING"},
    "CREATED":      {"AUTHORIZED", "CAPTURED", "FAILED", "RECONCILING"},
    "AUTHORIZED":   {"CAPTURED", "FAILED", "RECONCILING"},
    "RECONCILING":  {"CREATED", "AUTHORIZED", "CAPTURED", "FAILED", "DEAD_LETTER"},
    # Terminal states — no further transitions allowed
    "CAPTURED":     set(),
    "FAILED":       {"RECONCILING"},  # Failed can be retried via reconciliation
    "DEAD_LETTER":  set(),
}


def _is_legal_transition(current_state: str, new_state: str) -> bool:
    """Check if a payment state transition is legal."""
    allowed = LEGAL_TRANSITIONS.get(current_state, set())
    return new_state in allowed


def verify_signature(raw_body: bytes, received_signature: str) -> bool:
    """
    HMAC-SHA256 signature verification — hard gate.
    Uses raw body (not parsed JSON) to prevent signature mismatch.
    FAILS CLOSED: Rejects unsigned or improperly configured webhooks without exception.
    """
    if not received_signature:
        logger.warning("Webhook verification failed: missing x-razorpay-signature header (FAIL CLOSED)")
        return False

    settings = get_settings()
    if not settings.razorpay_webhook_secret:
        logger.error("Webhook verification failed: RAZORPAY_WEBHOOK_SECRET is not configured (FAIL CLOSED)")
        return False

    expected = hmac.new(
        settings.razorpay_webhook_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, received_signature)


def record_and_deduplicate_event(event_id: str, event_type: str, payload: dict) -> bool:
    """
    Atomically insert the event into webhook_events with ON CONFLICT DO NOTHING.
    Returns True if this is a NEW event (inserted successfully).
    Returns False if the event was ALREADY present (atomic deduplication, zero race conditions).
    """
    if not event_id:
        return True

    with get_db_transaction() as conn:
        cursor = conn.execute(
            """
            INSERT INTO webhook_events (event_id, event_type, payload_json, processed)
            VALUES (%s, %s, %s, 0)
            ON CONFLICT (event_id) DO NOTHING
            """,
            (event_id, event_type, json.dumps(payload)),
        )
        return cursor.rowcount == 1


def is_duplicate_event(event_id: str) -> bool:
    """Check if we've already processed this event (kept for backward compatibility)."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT processed FROM webhook_events WHERE event_id = %s",
            (event_id,),
        ).fetchone()
    return row is not None


def _validate_monetary_consistency(
    order_id: str,
    payment_entity: dict,
) -> tuple[bool, Optional[str]]:
    """
    Validate that webhook amount/currency matches local payment record.
    Returns (is_consistent, error_reason).
    """
    with get_db() as conn:
        local_record = conn.execute(
            "SELECT amount_paise, currency, session_id FROM payment_records WHERE razorpay_order_id = %s",
            (order_id,),
        ).fetchone()

    if not local_record:
        return False, f"Unknown order_id: {order_id} — no local payment record found"

    webhook_amount = payment_entity.get("amount")
    webhook_currency = payment_entity.get("currency", "").upper()
    local_amount = local_record["amount_paise"]
    local_currency = local_record["currency"].upper()

    if webhook_amount is not None and webhook_amount != local_amount:
        return False, (
            f"Amount mismatch: webhook={webhook_amount}, local={local_amount} "
            f"(order={order_id})"
        )

    if webhook_currency and webhook_currency != local_currency:
        return False, (
            f"Currency mismatch: webhook={webhook_currency}, local={local_currency} "
            f"(order={order_id})"
        )

    return True, None


def process_webhook_event(event_id: str, event_type: str, payload: dict) -> dict:
    """
    Process a verified, non-duplicate webhook event.

    Supported events:
    - payment.authorized: Update payment record status
    - payment.captured: Mark payment as complete
    - payment.failed: Trigger reconciliation
    - order.paid: Update order status
    """

    # Extract payment/order info from payload
    entity = payload.get("payload", {})
    payment_entity = entity.get("payment", {}).get("entity", {})
    order_entity = entity.get("order", {}).get("entity", {})

    order_id = payment_entity.get("order_id") or order_entity.get("id", "")
    payment_id = payment_entity.get("id", "")

    result = {"event_type": event_type, "event_id": event_id, "action": "none"}

    # ── Monetary consistency check ────────────────────────────────────────
    if order_id and payment_entity:
        is_consistent, mismatch_reason = _validate_monetary_consistency(order_id, payment_entity)
        if not is_consistent:
            logger.warning("Webhook monetary mismatch: %s", mismatch_reason)
            # Log mismatch to audit trail — do NOT mutate financial state
            with get_db() as conn:
                row = conn.execute(
                    "SELECT session_id FROM payment_records WHERE razorpay_order_id = %s",
                    (order_id,),
                ).fetchone()
                session_id = row["session_id"] if row else "unknown"

            with get_db_transaction() as conn:
                conn.execute(
                    """
                    INSERT INTO audit_log
                    (session_id, action, decision, failure_class, reason,
                     razorpay_order_id, razorpay_payment_id, actor, metadata_json)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        session_id,
                        "WEBHOOK_MISMATCH",
                        "REJECT",
                        "webhook-mismatch",
                        mismatch_reason,
                        order_id,
                        payment_id,
                        "razorpay",
                        json.dumps({"event_id": event_id, "event_type": event_type}),
                    ),
                )

            # Mark webhook as processed (with error)
            _mark_webhook_processed(event_id, error=mismatch_reason)

            result["action"] = "monetary_mismatch_rejected"
            return result

    # ── Process event with state machine enforcement ──────────────────────
    if event_type == "payment.authorized":
        _update_payment_status(order_id, payment_id, "AUTHORIZED")
        result["action"] = "updated_to_authorized"

    elif event_type == "payment.captured":
        _update_payment_status(order_id, payment_id, "CAPTURED")
        result["action"] = "updated_to_captured"

    elif event_type == "payment.failed":
        error_code = payment_entity.get("error_code", "unknown")
        _update_payment_status(order_id, payment_id, "FAILED", error=error_code)
        result["action"] = "marked_failed"

    elif event_type == "order.paid":
        _update_payment_status(order_id, "", "CAPTURED")
        result["action"] = "order_marked_paid"

    # Log to audit trail
    with get_db_transaction() as conn:
        # Find session_id from payment record
        row = conn.execute(
            "SELECT session_id FROM payment_records WHERE razorpay_order_id = %s",
            (order_id,),
        ).fetchone()
        session_id = row["session_id"] if row else "unknown"

        conn.execute(
            """
            INSERT INTO audit_log
            (session_id, action, decision, reason, razorpay_order_id,
             razorpay_payment_id, actor, metadata_json)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                session_id,
                "WEBHOOK_RECEIVED",
                "PASS",
                f"Webhook {event_type}: {result['action']}",
                order_id,
                payment_id,
                "razorpay",
                json.dumps({"event_id": event_id, "event_type": event_type}),
            ),
        )

    # Mark webhook as successfully processed
    _mark_webhook_processed(event_id)

    logger.info("Webhook processed: event=%s, type=%s, action=%s", event_id, event_type, result["action"])
    return result


def _mark_webhook_processed(event_id: str, error: Optional[str] = None) -> None:
    """Mark webhook event as processed with optional error."""
    if not event_id:
        return
    with get_db_transaction() as conn:
        if error:
            conn.execute(
                """
                UPDATE webhook_events
                SET processed = 1, processing_attempts = processing_attempts + 1,
                    last_error = %s, processed_at = CURRENT_TIMESTAMP
                WHERE event_id = %s
                """,
                (error, event_id),
            )
        else:
            conn.execute(
                """
                UPDATE webhook_events
                SET processed = 1, processing_attempts = processing_attempts + 1,
                    processed_at = CURRENT_TIMESTAMP
                WHERE event_id = %s
                """,
                (event_id,),
            )


def _update_payment_status(
    order_id: str,
    payment_id: str,
    new_status: str,
    error: Optional[str] = None,
) -> None:
    """Update payment record with state machine enforcement."""
    with get_db_transaction() as conn:
        # Fetch current state for state machine validation
        current = conn.execute(
            "SELECT status, session_id FROM payment_records WHERE razorpay_order_id = %s",
            (order_id,),
        ).fetchone()

        if not current:
            logger.warning("Webhook references unknown order: %s", order_id)
            return

        current_status = current["status"]

        # ── State machine gate ────────────────────────────────────────────
        if not _is_legal_transition(current_status, new_status):
            logger.warning(
                "Illegal payment state transition blocked: %s -> %s (order=%s)",
                current_status, new_status, order_id,
            )
            # Log to audit trail
            conn.execute(
                """
                INSERT INTO audit_log
                (session_id, action, decision, failure_class, reason,
                 razorpay_order_id, actor)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    current["session_id"],
                    "PAYMENT_STATE_VIOLATION",
                    "REJECT",
                    "webhook-mismatch",
                    f"Illegal transition: {current_status} -> {new_status}",
                    order_id,
                    "system",
                ),
            )
            return

        # ── Perform the state update ──────────────────────────────────────
        if payment_id:
            conn.execute(
                """
                UPDATE payment_records
                SET status = %s, razorpay_payment_id = %s,
                    last_error = COALESCE(%s, last_error),
                    updated_at = CURRENT_TIMESTAMP
                WHERE razorpay_order_id = %s
                """,
                (new_status, payment_id, error, order_id),
            )
        else:
            conn.execute(
                """
                UPDATE payment_records
                SET status = %s, last_error = COALESCE(%s, last_error),
                    updated_at = CURRENT_TIMESTAMP
                WHERE razorpay_order_id = %s
                """,
                (new_status, error, order_id),
            )
