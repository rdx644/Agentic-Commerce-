"""
Central payment state machine — single authoritative gate for payment_records.status mutations.

Every state transition across payment service, webhooks, reconciliation, and dead-letter
handling MUST go through transition_payment_state().
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from src.database import get_db, get_db_transaction

logger = logging.getLogger(__name__)

PAYMENT_STATES = {
    "PENDING",
    "CREATED",
    "AUTHORIZED",
    "CAPTURED",
    "FAILED",
    "RECONCILING",
    "DEAD_LETTER",
}

LEGAL_TRANSITIONS: dict[str, set[str]] = {
    "PENDING": {"CREATED", "FAILED", "RECONCILING", "DEAD_LETTER"},
    "CREATED": {"AUTHORIZED", "CAPTURED", "FAILED", "RECONCILING", "DEAD_LETTER"},
    "AUTHORIZED": {"CAPTURED", "FAILED", "RECONCILING", "DEAD_LETTER"},
    "RECONCILING": {"CREATED", "AUTHORIZED", "CAPTURED", "FAILED", "DEAD_LETTER"},
    "CAPTURED": set(),  # Terminal state — no regressions allowed
    "FAILED": {"RECONCILING", "DEAD_LETTER"},  # Can enter reconciliation or DLQ, cannot directly revert to CAPTURED
    "DEAD_LETTER": set(),  # Terminal state
}


class PaymentStateTransitionError(ValueError):
    """Raised when an illegal payment state transition is attempted."""
    pass


class PaymentIdMismatchError(ValueError):
    """Raised when attempting to overwrite an existing payment ID with a conflicting one."""
    pass


def is_legal_transition(current_status: str, new_status: str) -> bool:
    """Check if transition from current_status to new_status is allowed."""
    if current_status == new_status:
        return True  # Idempotent re-affirmation
    return new_status in LEGAL_TRANSITIONS.get(current_status, set())


def transition_payment_state(
    payment_record_id: Optional[int] = None,
    new_status: str = "",
    *,
    razorpay_order_id: Optional[str] = None,
    razorpay_payment_id: Optional[str] = None,
    actor: str = "system",
    reason: Optional[str] = None,
    error: Optional[str] = None,
    increment_attempts: bool = False,
) -> dict:
    """
    Centralized, authoritative payment state transition.

    Enforces:
    1. Existence of payment record.
    2. Idempotent success when new_status == current_status.
    3. Payment ID consistency (rejects overwriting existing ID with a conflicting ID).
    4. Transition validity (blocks illegal regressions such as CAPTURED -> PENDING).
    5. Atomic database persistence.
    6. Audit trail logging for all transitions and violations.
    """
    if new_status not in PAYMENT_STATES:
        raise ValueError(f"Invalid payment status '{new_status}'. Allowed: {PAYMENT_STATES}")

    if payment_record_id is None and not razorpay_order_id:
        raise ValueError("Must provide either payment_record_id or razorpay_order_id to transition state.")

    # ── Fetch current record ──────────────────────────────────────────────────
    with get_db() as conn:
        if payment_record_id is not None:
            row = conn.execute(
                "SELECT * FROM payment_records WHERE id = %s",
                (payment_record_id,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM payment_records WHERE razorpay_order_id = %s",
                (razorpay_order_id,),
            ).fetchone()

    if not row:
        target = f"id={payment_record_id}" if payment_record_id else f"order_id={razorpay_order_id}"
        raise ValueError(f"Payment record not found for {target}")

    record = dict(row)
    rec_id = record["id"]
    session_id = record["session_id"]
    current_status = record["status"]
    existing_pay_id = record.get("razorpay_payment_id")
    order_id = record.get("razorpay_order_id") or razorpay_order_id

    # ── Check Payment ID Consistency ──────────────────────────────────────────
    if razorpay_payment_id and existing_pay_id and existing_pay_id != razorpay_payment_id:
        mismatch_msg = (
            f"Conflicting payment ID for order {order_id}: "
            f"existing={existing_pay_id}, incoming={razorpay_payment_id}"
        )
        logger.error("Security mismatch: %s", mismatch_msg)
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
                    "PAYMENT_ID_MISMATCH",
                    "REJECT",
                    "security-violation",
                    mismatch_msg,
                    order_id,
                    razorpay_payment_id,
                    actor,
                    json.dumps({
                        "existing_payment_id": existing_pay_id,
                        "incoming_payment_id": razorpay_payment_id,
                    }),
                ),
            )
        raise PaymentIdMismatchError(mismatch_msg)

    # ── Check Idempotency (same status) ───────────────────────────────────────
    if current_status == new_status:
        # If new payment_id or order_id is provided, backfill it atomically
        if (razorpay_payment_id and not existing_pay_id) or (razorpay_order_id and not record.get("razorpay_order_id")):
            with get_db_transaction() as conn:
                conn.execute(
                    """
                    UPDATE payment_records
                    SET razorpay_payment_id = COALESCE(razorpay_payment_id, %s),
                        razorpay_order_id = COALESCE(razorpay_order_id, %s),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    """,
                    (razorpay_payment_id, razorpay_order_id, rec_id),
                )
        return record

    # ── Enforce Legal State Transition ────────────────────────────────────────
    if not is_legal_transition(current_status, new_status):
        violation_msg = f"Illegal payment transition from {current_status} to {new_status} (record={rec_id})"
        logger.error("State violation: %s", violation_msg)
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
                    "PAYMENT_STATE_VIOLATION",
                    "REJECT",
                    "illegal-transition",
                    violation_msg,
                    order_id,
                    razorpay_payment_id or existing_pay_id,
                    actor,
                    json.dumps({
                        "current_status": current_status,
                        "attempted_status": new_status,
                        "reason": reason,
                    }),
                ),
            )
        raise PaymentStateTransitionError(violation_msg)

    # ── Execute State Mutation Atomically ─────────────────────────────────────
    attempts_sql = "attempts = attempts + 1," if increment_attempts else ""
    with get_db_transaction() as conn:
        conn.execute(
            f"""
            UPDATE payment_records
            SET status = %s,
                razorpay_order_id = COALESCE(razorpay_order_id, %s),
                razorpay_payment_id = COALESCE(razorpay_payment_id, %s),
                last_error = COALESCE(%s, last_error),
                {attempts_sql}
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (new_status, razorpay_order_id, razorpay_payment_id, error, rec_id),
        )

        conn.execute(
            """
            INSERT INTO audit_log
            (session_id, action, decision, reason, razorpay_order_id,
             razorpay_payment_id, actor, metadata_json)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                session_id,
                "PAYMENT_STATE_TRANSITION",
                "PASS",
                reason or f"Transition: {current_status} -> {new_status}",
                order_id,
                razorpay_payment_id or existing_pay_id,
                actor,
                json.dumps({
                    "from_status": current_status,
                    "to_status": new_status,
                    "actor": actor,
                    "error": error,
                }),
            ),
        )

    # Fetch and return updated record
    with get_db() as conn:
        updated = conn.execute("SELECT * FROM payment_records WHERE id = %s", (rec_id,)).fetchone()
    return dict(updated) if updated else record
