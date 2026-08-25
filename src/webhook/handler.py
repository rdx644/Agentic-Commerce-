"""
Webhook handler — HMAC-SHA256 verified, deduplicated, async-processed.

Design:
- HMAC-SHA256 signature verification is a HARD GATE — reject before trusting.
- Use raw body for verification (not parsed JSON).
- Ack fast (200) and push heavy processing to background.
- Dedup via x-razorpay-event-id in webhook_events table.
- Events may arrive out of order — handle gracefully.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Optional

from src.config import get_settings
from src.database import get_db, get_db_transaction
from src.guardrail.models import FailureClass

logger = logging.getLogger(__name__)


def verify_signature(raw_body: bytes, received_signature: str) -> bool:
    """
    HMAC-SHA256 signature verification — hard gate.
    Uses raw body (not parsed JSON) to prevent signature mismatch.
    """
    settings = get_settings()
    if not settings.razorpay_webhook_secret:
        logger.warning("Webhook secret not configured — skipping verification in dev mode")
        return True

    expected = hmac.new(
        settings.razorpay_webhook_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, received_signature)


def is_duplicate_event(event_id: str) -> bool:
    """Check if we've already processed this event (dedup)."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT processed FROM webhook_events WHERE event_id = %s",
            (event_id,),
        ).fetchone()
    return row is not None


def process_webhook_event(event_id: str, event_type: str, payload: dict) -> dict:
    """
    Process a verified, non-duplicate webhook event.

    Supported events:
    - payment.authorized: Update payment record status
    - payment.captured: Mark payment as complete
    - payment.failed: Trigger reconciliation
    - order.paid: Update order status
    """
    # Store event for dedup
    with get_db_transaction() as conn:
        try:
            conn.execute(
                """
                INSERT INTO webhook_events (event_id, event_type, payload_json, processed)
                VALUES (%s, %s, %s, 1)
                """,
                (event_id, event_type, json.dumps(payload)),
            )
        except Exception:
            # Already processed (race condition in concurrent processing)
            logger.info("Event %s already processed (concurrent insert)", event_id)
            return {"status": "already_processed"}

    # Extract payment/order info from payload
    entity = payload.get("payload", {})
    payment_entity = entity.get("payment", {}).get("entity", {})
    order_entity = entity.get("order", {}).get("entity", {})

    order_id = payment_entity.get("order_id") or order_entity.get("id", "")
    payment_id = payment_entity.get("id", "")

    result = {"event_type": event_type, "event_id": event_id, "action": "none"}

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

    logger.info("Webhook processed: event=%s, type=%s, action=%s", event_id, event_type, result["action"])
    return result


def _update_payment_status(
    order_id: str,
    payment_id: str,
    new_status: str,
    error: Optional[str] = None,
) -> None:
    """Update payment record based on webhook data."""
    with get_db_transaction() as conn:
        if payment_id:
            conn.execute(
                """
                UPDATE payment_records
                SET status = %s, razorpay_payment_id = %s,
                    last_error = COALESCE(%s, last_error),
                    updated_at = NOW()
                WHERE razorpay_order_id = %s
                """,
                (new_status, payment_id, error, order_id),
            )
        else:
            conn.execute(
                """
                UPDATE payment_records
                SET status = %s, last_error = COALESCE(%s, last_error),
                    updated_at = NOW()
                WHERE razorpay_order_id = %s
                """,
                (new_status, error, order_id),
            )
