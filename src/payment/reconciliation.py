"""
Reconciliation service — the proof point for "one failure handled gracefully."

Handles the network-timeout-mid-payment case:
1. Detect: our ledger says PENDING/CREATED but we lost the response
2. Reconcile: poll Razorpay's order/payment fetch endpoint as source of truth
3. Correct: update our ledger to match Razorpay's state
4. Dead-letter: after N failed attempts, move to manual review (never silently drop)

Retry policy:
- Exponential backoff with full jitter on transient Razorpay errors
- NEVER retry a guardrail rejection
- Auto-discover stale PENDING records older than configurable threshold
"""

from __future__ import annotations

import json
import logging
import random
import time
from datetime import datetime, timezone
from typing import Optional

from src.config import get_settings
from src.database import get_db, get_db_transaction
from src.guardrail.models import FailureClass
from src.payment.models import ReconciliationResult
from src.payment import service as payment_service
from src.payment.workflow import compute_backoff_delay

logger = logging.getLogger(__name__)

# Stale threshold: records older than this (seconds) are auto-discovered
STALE_PENDING_THRESHOLD_SECONDS = 300  # 5 minutes


def reconcile_payment(payment_record_id: int) -> ReconciliationResult:
    """
    Reconcile a single payment record against Razorpay's source of truth.
    """
    settings = get_settings()

    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM payment_records WHERE id = %s",
            (payment_record_id,),
        ).fetchone()

    if row is None:
        raise ValueError(f"Payment record {payment_record_id} not found")

    session_id = row["session_id"]
    razorpay_order_id = row["razorpay_order_id"]
    local_status = row["status"]
    attempts = row["attempts"]

    # If no Razorpay order ID, we never got through — can't reconcile
    if not razorpay_order_id:
        if attempts >= settings.max_reconciliation_attempts:
            _dead_letter(payment_record_id, session_id, "No Razorpay order ID after max attempts", attempts)
            return ReconciliationResult(
                payment_record_id=payment_record_id,
                session_id=session_id,
                razorpay_order_id="",
                local_status=local_status,
                razorpay_status="unknown",
                reconciled=False,
                action_taken="Dead-lettered: no Razorpay order ID",
                dead_lettered=True,
            )
        return ReconciliationResult(
            payment_record_id=payment_record_id,
            session_id=session_id,
            razorpay_order_id="",
            local_status=local_status,
            razorpay_status="unknown",
            reconciled=False,
            action_taken="Skipped: no Razorpay order ID to reconcile against",
        )

    # Fetch from Razorpay — THE source of truth
    razorpay_order = payment_service.fetch_order_from_razorpay(razorpay_order_id)

    if razorpay_order is None:
        # Network failure fetching from Razorpay
        if attempts >= settings.max_reconciliation_attempts:
            _dead_letter(
                payment_record_id, session_id,
                f"Cannot reach Razorpay to reconcile order {razorpay_order_id}",
                attempts,
            )
            return ReconciliationResult(
                payment_record_id=payment_record_id,
                session_id=session_id,
                razorpay_order_id=razorpay_order_id,
                local_status=local_status,
                razorpay_status="unreachable",
                reconciled=False,
                action_taken="Dead-lettered: Razorpay unreachable",
                dead_lettered=True,
            )
        return ReconciliationResult(
            payment_record_id=payment_record_id,
            session_id=session_id,
            razorpay_order_id=razorpay_order_id,
            local_status=local_status,
            razorpay_status="unreachable",
            reconciled=False,
            action_taken="Retry needed: Razorpay unreachable",
        )

    # Compare our state with Razorpay's truth
    rzp_status = razorpay_order.get("status", "unknown")

    # Map Razorpay status to our status
    status_map = {
        "created": "CREATED",
        "attempted": "CREATED",
        "paid": "CAPTURED",
    }
    correct_status = status_map.get(rzp_status, local_status)

    if correct_status != local_status:
        # Our ledger is wrong — correct it
        with get_db_transaction() as conn:
            conn.execute(
                """
                UPDATE payment_records
                SET status = %s, attempts = attempts + 1, updated_at = NOW()
                WHERE id = %s
                """,
                (correct_status, payment_record_id),
            )

        # Log the reconciliation correction to audit trail
        with get_db_transaction() as conn:
            conn.execute(
                """
                INSERT INTO audit_log
                (session_id, action, decision, reason, razorpay_order_id,
                 actor, metadata_json)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    session_id,
                    "RECONCILIATION",
                    "PASS",
                    f"Corrected: {local_status} → {correct_status} (Razorpay: {rzp_status})",
                    razorpay_order_id,
                    "system",
                    json.dumps({
                        "local_status_before": local_status,
                        "razorpay_status": rzp_status,
                        "corrected_to": correct_status,
                    }),
                ),
            )

        logger.info(
            "Reconciliation corrected: order=%s, %s → %s",
            razorpay_order_id, local_status, correct_status,
        )

        return ReconciliationResult(
            payment_record_id=payment_record_id,
            session_id=session_id,
            razorpay_order_id=razorpay_order_id,
            local_status=correct_status,
            razorpay_status=rzp_status,
            reconciled=True,
            action_taken=f"Corrected: {local_status} → {correct_status}",
        )

    return ReconciliationResult(
        payment_record_id=payment_record_id,
        session_id=session_id,
        razorpay_order_id=razorpay_order_id,
        local_status=local_status,
        razorpay_status=rzp_status,
        reconciled=True,
        action_taken="Already consistent",
    )


def reconcile_all_pending() -> list[ReconciliationResult]:
    """
    Reconcile all PENDING/CREATED payment records with backoff between attempts.
    Uses exponential backoff to avoid hammering Razorpay.
    """
    settings = get_settings()

    with get_db() as conn:
        rows = conn.execute(
            "SELECT id FROM payment_records WHERE status IN ('PENDING', 'CREATED')"
        ).fetchall()

    results = []
    for i, row in enumerate(rows):
        try:
            result = reconcile_payment(row["id"])
            results.append(result)

            # Apply backoff between records to avoid Razorpay rate limits
            if i < len(rows) - 1:
                delay = compute_backoff_delay(
                    attempt=0,  # Light backoff between records
                    base=settings.retry_base_delay_seconds,
                    max_delay=5.0,
                )
                time.sleep(delay)

        except Exception as e:
            logger.error("Reconciliation failed for record %d: %s", row["id"], e)

    logger.info(
        "Reconciliation batch complete: %d records processed, %d reconciled, %d dead-lettered",
        len(results),
        sum(1 for r in results if r.reconciled),
        sum(1 for r in results if r.dead_lettered),
    )
    return results


def discover_stale_pending(threshold_seconds: int = STALE_PENDING_THRESHOLD_SECONDS) -> list[int]:
    """
    Auto-discover PENDING/CREATED records older than threshold.

    These are likely orphaned by network failures between writing
    the PENDING record and receiving Razorpay's response.

    Returns list of payment_record_ids that need reconciliation.
    """
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT id, session_id, idempotency_key, created_at
            FROM payment_records
            WHERE status IN ('PENDING', 'CREATED')
            AND created_at < NOW() - (%s || ' seconds')::interval
            """,
            (f"-{threshold_seconds}",),
        ).fetchall()

    stale_ids = [row["id"] for row in rows]

    if stale_ids:
        logger.warning(
            "Discovered %d stale PENDING records (older than %ds): %s",
            len(stale_ids), threshold_seconds, stale_ids,
        )

    return stale_ids


def reconcile_stale() -> list[ReconciliationResult]:
    """
    Discover and reconcile all stale PENDING records.
    Combines auto-discovery with reconciliation.
    """
    stale_ids = discover_stale_pending()
    results = []
    for record_id in stale_ids:
        try:
            result = reconcile_payment(record_id)
            results.append(result)
        except Exception as e:
            logger.error("Stale reconciliation failed for record %d: %s", record_id, e)
    return results


def _dead_letter(
    payment_record_id: int,
    session_id: str,
    reason: str,
    attempts: int,
) -> None:
    """Move a failed payment to the dead-letter queue for manual review."""
    with get_db_transaction() as conn:
        conn.execute(
            """
            INSERT INTO dead_letter_queue
            (session_id, payment_record_id, failure_class, reason, attempts)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (session_id, payment_record_id, FailureClass.RECONCILIATION_FAIL.value, reason, attempts),
        )

        conn.execute(
            "UPDATE payment_records SET status = 'DEAD_LETTER' WHERE id = %s",
            (payment_record_id,),
        )

        # Audit log entry
        conn.execute(
            """
            INSERT INTO audit_log
            (session_id, action, decision, failure_class, reason, actor, metadata_json)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                session_id,
                "DEAD_LETTER",
                "REJECT",
                FailureClass.RECONCILIATION_FAIL.value,
                reason,
                "system",
                json.dumps({"payment_record_id": payment_record_id, "attempts": attempts}),
            ),
        )

    logger.warning(
        "Payment dead-lettered: record=%d, session=%s, reason=%s",
        payment_record_id, session_id, reason,
    )
