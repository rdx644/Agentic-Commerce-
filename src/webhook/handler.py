"""
Webhook handler — HMAC-SHA256 verified, deduplicated, with monetary validation and durable recovery.

Design:
- HMAC-SHA256 signature verification is a HARD GATE — reject before trusting.
- Use raw body for verification (not parsed JSON).
- Dedup via x-razorpay-event-id in webhook_events table.
- Events may arrive out of order — handled gracefully via central state machine.
- Monetary consistency: webhook amount/currency must match local record.
- order.paid: validated against order/payment monetary identity before capture.
- Durable processing state: RECEIVED -> PROCESSING -> PROCESSED / FAILED -> DEAD_LETTER.
- recover_failed_webhooks(): discovers un-processed events and safely retries.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Optional

from src.config import get_settings
from src.database import get_db, get_db_transaction
from src.payment.state_machine import transition_payment_state

logger = logging.getLogger(__name__)


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
    Sets processing_status to 'RECEIVED' for durable recovery tracking.
    """
    if not event_id:
        return True

    with get_db_transaction() as conn:
        cursor = conn.execute(
            """
            INSERT INTO webhook_events (event_id, event_type, payload_json, processed, processing_status)
            VALUES (%s, %s, %s, 0, 'RECEIVED')
            ON CONFLICT (event_id) DO NOTHING
            """,
            (event_id, event_type, json.dumps(payload)),
        )
        return cursor.rowcount == 1


def is_duplicate_event(event_id: str) -> bool:
    """Check if we've already recorded this event."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT processed FROM webhook_events WHERE event_id = %s",
            (event_id,),
        ).fetchone()
    return row is not None


def _validate_monetary_consistency(
    order_id: str,
    entity_dict: dict,
) -> tuple[bool, Optional[str]]:
    """
    Validate that webhook amount/currency matches local payment record.
    FAILS CLOSED: Missing, malformed, or mismatched financial fields are strictly rejected.
    """
    if not order_id:
        return False, "Missing order_id for monetary validation"

    with get_db() as conn:
        local_record = conn.execute(
            "SELECT amount_paise, currency, session_id FROM payment_records WHERE razorpay_order_id = %s",
            (order_id,),
        ).fetchone()

    if not local_record:
        return False, f"Unknown order_id: {order_id} — no local payment record found"

    raw_amount = entity_dict.get("amount")
    raw_currency = entity_dict.get("currency")

    # Fail closed on missing financial fields
    if raw_amount is None:
        return False, f"Missing amount in webhook payload (order={order_id})"
    try:
        webhook_amount = int(raw_amount)
    except (ValueError, TypeError):
        return False, f"Malformed amount in webhook payload: {raw_amount} (order={order_id})"

    if not raw_currency or not isinstance(raw_currency, str):
        return False, f"Missing or malformed currency in webhook payload (order={order_id})"

    webhook_currency = raw_currency.strip().upper()
    local_amount = local_record["amount_paise"]
    local_currency = local_record["currency"].upper()

    if webhook_amount != local_amount:
        return False, (
            f"Amount mismatch: webhook={webhook_amount}, local={local_amount} "
            f"(order={order_id})"
        )

    if webhook_currency != local_currency:
        return False, (
            f"Currency mismatch: webhook={webhook_currency}, local={local_currency} "
            f"(order={order_id})"
        )

    return True, None


def _log_webhook_mismatch(order_id: str, payment_id: str, event_id: str, event_type: str, reason: str) -> None:
    """Helper to log webhook monetary or identity mismatch to audit trail."""
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
                reason,
                order_id,
                payment_id,
                "razorpay",
                json.dumps({"event_id": event_id, "event_type": event_type}),
            ),
        )


def process_webhook_event(event_id: str, event_type: str, payload: dict) -> dict:
    """
    Process a verified, non-duplicate webhook event with fail-closed financial validation.
    """
    entity = payload.get("payload", {})
    payment_entity = entity.get("payment", {}).get("entity", {})
    order_entity = entity.get("order", {}).get("entity", {})

    order_id = payment_entity.get("order_id") or order_entity.get("id", "")
    payment_id = payment_entity.get("id", "")

    result = {"event_type": event_type, "event_id": event_id, "action": "none"}

    # ── Handle order.paid ─────────────────────────────────────────────────────
    if event_type == "order.paid":
        target_entity = payment_entity if payment_entity.get("amount") is not None else order_entity
        if not target_entity or target_entity.get("amount") is None or not target_entity.get("currency"):
            mismatch_reason = f"Missing required financial fields for order.paid (order={order_id})"
            logger.warning("Webhook monetary validation failed: %s", mismatch_reason)
            _log_webhook_mismatch(order_id, payment_id, event_id, event_type, mismatch_reason)
            _mark_webhook_processed(event_id, error=mismatch_reason, status="FAILED")
            result["action"] = "monetary_mismatch_rejected"
            return result

        is_consistent, mismatch_reason = _validate_monetary_consistency(order_id, target_entity)
        if not is_consistent:
            logger.warning("Webhook monetary mismatch: %s", mismatch_reason)
            _log_webhook_mismatch(order_id, payment_id, event_id, event_type, mismatch_reason)
            _mark_webhook_processed(event_id, error=mismatch_reason, status="FAILED")
            result["action"] = "monetary_mismatch_rejected"
            return result

        # If payment_entity present, check order_id consistency
        if payment_entity and payment_entity.get("order_id") and payment_entity.get("order_id") != order_id:
            mismatch_reason = f"Order ID mismatch in payment entity: {payment_entity.get('order_id')} != {order_id}"
            logger.warning(mismatch_reason)
            _log_webhook_mismatch(order_id, payment_id, event_id, event_type, mismatch_reason)
            _mark_webhook_processed(event_id, error=mismatch_reason, status="FAILED")
            result["action"] = "monetary_mismatch_rejected"
            return result

        _update_payment_status(order_id, payment_id, "CAPTURED")
        result["action"] = "order_marked_paid"

    # ── Handle payment.* events ───────────────────────────────────────────────
    elif event_type in ("payment.authorized", "payment.captured", "payment.failed"):
        if not payment_entity or payment_entity.get("amount") is None or not payment_entity.get("currency"):
            mismatch_reason = f"Missing required financial fields for {event_type} (order={order_id})"
            logger.warning("Webhook monetary validation failed: %s", mismatch_reason)
            _log_webhook_mismatch(order_id, payment_id, event_id, event_type, mismatch_reason)
            _mark_webhook_processed(event_id, error=mismatch_reason, status="FAILED")
            result["action"] = "monetary_mismatch_rejected"
            return result

        is_consistent, mismatch_reason = _validate_monetary_consistency(order_id, payment_entity)
        if not is_consistent:
            logger.warning("Webhook monetary mismatch: %s", mismatch_reason)
            _log_webhook_mismatch(order_id, payment_id, event_id, event_type, mismatch_reason)
            _mark_webhook_processed(event_id, error=mismatch_reason, status="FAILED")
            result["action"] = "monetary_mismatch_rejected"
            return result

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

    # Log successful webhook receipt to audit trail
    with get_db_transaction() as conn:
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
    _mark_webhook_processed(event_id, status="PROCESSED")

    logger.info("Webhook processed: event=%s, type=%s, action=%s", event_id, event_type, result["action"])
    return result


def _mark_webhook_processed(
    event_id: str,
    error: Optional[str] = None,
    status: str = "PROCESSED",
) -> None:
    """Mark webhook event with durable processing status and error tracking."""
    if not event_id:
        return
    with get_db_transaction() as conn:
        conn.execute(
            """
            UPDATE webhook_events
            SET processed = %s,
                processing_status = %s,
                processing_attempts = processing_attempts + 1,
                last_error = %s,
                processed_at = CURRENT_TIMESTAMP
            WHERE event_id = %s
            """,
            (1 if status == "PROCESSED" else 0, status, error, event_id),
        )


def _update_payment_status(
    order_id: str,
    payment_id: str,
    new_status: str,
    error: Optional[str] = None,
) -> None:
    """Update payment record via the central payment state machine."""
    try:
        transition_payment_state(
            razorpay_order_id=order_id,
            new_status=new_status,
            razorpay_payment_id=payment_id if payment_id else None,
            actor="webhook",
            reason=f"Webhook event transition to {new_status}",
            error=error,
        )
    except Exception as exc:
        logger.warning("Payment state transition rejected for order %s: %s", order_id, exc)


def recover_failed_webhooks(max_attempts: int = 3) -> list[dict]:
    """
    Durable recovery routine for webhook events.
    Discovers webhook events with processed = 0, re-executes them,
    and moves exhausted events to DEAD_LETTER status.
    """
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT event_id, event_type, payload_json, processing_attempts
            FROM webhook_events
            WHERE processed = 0 AND processing_status != 'DEAD_LETTER'
            ORDER BY created_at ASC
            LIMIT 50
            """
        ).fetchall()

    results = []
    for row in rows:
        event_id = row["event_id"]
        event_type = row["event_type"]
        attempts = row["processing_attempts"]

        if attempts >= max_attempts:
            logger.warning("Exhausted retries for webhook %s; dead-lettering", event_id)
            _mark_webhook_processed(event_id, error="Exhausted maximum retry attempts", status="DEAD_LETTER")
            results.append({"event_id": event_id, "action": "dead_lettered"})
            continue

        try:
            payload = json.loads(row["payload_json"])
            res = process_webhook_event(event_id, event_type, payload)
            results.append(res)
        except Exception as e:
            logger.error("Recovery failed for webhook %s: %s", event_id, e)
            _mark_webhook_processed(event_id, error=str(e), status="FAILED")
            results.append({"event_id": event_id, "action": "failed", "error": str(e)})

    return results
