"""
Payment service — Razorpay order creation with idempotency.

Design invariants:
- Capability token REQUIRED — no token, no Razorpay call.
- Idempotency key = receipt field (Razorpay's mechanism for Orders API).
- Write to OUR ledger BEFORE calling Razorpay.
- Handle 400 "Duplicate request" as success (idempotent).
- On any ambiguous network state, Razorpay's fetch endpoint is truth.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Optional

import razorpay

from src.config import get_settings
from src.database import get_db, get_db_transaction
from src.guardrail.models import FailureClass
from src.payment.models import PaymentDispatchRequest, PaymentDispatchResponse
from src.security.tokens import verify_capability_token, consume_capability_token

logger = logging.getLogger(__name__)

# ── Razorpay client (lazy init) ──────────────────────────────────────────────

_razorpay_client: Optional[razorpay.Client] = None


def _get_razorpay_client() -> razorpay.Client:
    """Lazy-init Razorpay client with test-mode keys."""
    global _razorpay_client
    if _razorpay_client is None:
        settings = get_settings()
        _razorpay_client = razorpay.Client(
            auth=(settings.razorpay_key_id, settings.razorpay_key_secret)
        )
    return _razorpay_client


def _generate_idempotency_key(session_id: str, token_id: str) -> str:
    """
    Deterministic idempotency key from the one-time payment authority.
    A fresh guardrail pass creates a new token and therefore a new receipt.
    """
    raw = f"s:{session_id}:t:{token_id}"
    hashed = hashlib.sha256(raw.encode()).hexdigest()[:24]
    return f"ac_{hashed}"  # 27 chars, well within 40-char limit


def _log_payment_action(
    session_id: str,
    action: str,
    razorpay_order_id: Optional[str] = None,
    razorpay_payment_id: Optional[str] = None,
    amount_paise: Optional[int] = None,
    failure_class: Optional[FailureClass] = None,
    reason: str = "",
    metadata: Optional[dict] = None,
) -> None:
    """Log payment action to audit trail."""
    with get_db_transaction() as conn:
        conn.execute(
            """
            INSERT INTO audit_log
            (session_id, action, decision, failure_class, reason, amount_paise,
             actor, razorpay_order_id, razorpay_payment_id, metadata_json)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                session_id,
                action,
                "PASS" if failure_class is None else "REJECT",
                failure_class.value if failure_class else None,
                reason,
                amount_paise,
                "system",
                razorpay_order_id,
                razorpay_payment_id,
                json.dumps(metadata) if metadata else None,
            ),
        )


def dispatch_payment(request: PaymentDispatchRequest) -> PaymentDispatchResponse:
    """
    Dispatch payment to Razorpay with full guardrail verification.

    Flow:
    1. Verify capability token (JWT signature + expiry)
    2. Generate idempotency key
    3. Write PENDING record to our ledger
    4. Call Razorpay Orders API
    5. Handle success / duplicate / failure
    """
    session_id = request.session_id

    # ── Step 1: Verify capability token ───────────────────────────────────
    token_payload = verify_capability_token(request.capability_token)
    if token_payload is None:
        _log_payment_action(
            session_id, "PAYMENT_DISPATCH",
            failure_class=FailureClass.TOKEN_EXPIRED,
            reason="Capability token expired or invalid",
            amount_paise=request.amount_paise,
        )
        return PaymentDispatchResponse(
            session_id=session_id,
            success=False,
            status="REJECTED",
            message="Capability token expired or invalid. Re-run guardrail check.",
        )

    if token_payload.session_id != session_id:
        _log_payment_action(
            session_id, "PAYMENT_DISPATCH",
            failure_class=FailureClass.TOKEN_INVALID,
            reason="Token session_id mismatch",
            amount_paise=request.amount_paise,
        )
        return PaymentDispatchResponse(
            session_id=session_id,
            success=False,
            status="REJECTED",
            message="Token session mismatch.",
        )

    if request.amount_paise != token_payload.max_spend_paise:
        _log_payment_action(
            session_id, "PAYMENT_DISPATCH",
            failure_class=FailureClass.BUDGET_EXCEEDED,
            reason=(
                f"Amount {request.amount_paise} does not match the token's "
                f"authorised amount {token_payload.max_spend_paise}"
            ),
            amount_paise=request.amount_paise,
        )
        return PaymentDispatchResponse(
            session_id=session_id,
            success=False,
            status="REJECTED",
            message="Payment amount must exactly match the capability token authorisation.",
        )

    # ── Step 2: Generate idempotency key ──────────────────────────────────
    idempotency_key = _generate_idempotency_key(session_id, token_payload.token_id)

    # ── Step 3: Atomically consume the capability token (single-use) ──────
    # First check: is this an idempotent retry of the same request?
    with get_db() as conn:
        existing = conn.execute(
            "SELECT * FROM payment_records WHERE idempotency_key = %s",
            (idempotency_key,),
        ).fetchone()
        if existing and existing["razorpay_order_id"]:
            logger.info("Idempotent hit: returning existing order %s", existing["razorpay_order_id"])
            return PaymentDispatchResponse(
                session_id=session_id,
                success=True,
                razorpay_order_id=existing["razorpay_order_id"],
                idempotency_key=idempotency_key,
                amount_paise=request.amount_paise,
                currency=request.currency,
                status=existing["status"],
                message="Idempotent: returning existing order.",
                payment_record_id=existing["id"],
            )

    # Now consume — only proceeds if token has NOT been consumed yet
    if not consume_capability_token(token_payload.token_id):
        # Token is already consumed, expired, or nonexistent
        # But was this our own idempotent retry? Check if we have a pending record
        with get_db() as conn:
            pending = conn.execute(
                "SELECT * FROM payment_records WHERE idempotency_key = %s",
                (idempotency_key,),
            ).fetchone()
        if pending:
            # Same token, same session — this is a retry of a pending payment
            logger.info("Capability already consumed but payment pending — allowing retry")
        else:
            _log_payment_action(
                session_id, "PAYMENT_DISPATCH",
                failure_class=FailureClass.TOKEN_INVALID,
                reason="Capability token already consumed or expired (single-use enforcement)",
                amount_paise=request.amount_paise,
            )
            return PaymentDispatchResponse(
                session_id=session_id,
                success=False,
                status="REJECTED",
                message="Capability token already consumed. Each authorization is single-use.",
            )

    # ── Step 4: Write PENDING to our ledger BEFORE calling Razorpay ───────
    with get_db_transaction() as conn:
        conn.execute(
            """
            INSERT INTO payment_records
            (session_id, idempotency_key, amount_paise, currency, status, capability_token_id)
            VALUES (%s, %s, %s, %s, 'PENDING', %s)
            ON CONFLICT (idempotency_key) DO NOTHING
            """,
            (session_id, idempotency_key, request.amount_paise, request.currency, token_payload.token_id),
        )

    # ── Step 4: Call Razorpay Orders API ──────────────────────────────────
    client = _get_razorpay_client()
    try:
        order = client.order.create({
            "amount": request.amount_paise,
            "currency": request.currency,
            "receipt": idempotency_key,
            "payment_capture": 1,  # Auto-capture in test mode
        })

        razorpay_order_id = order["id"]

        # Update our record with Razorpay's order ID
        with get_db_transaction() as conn:
            conn.execute(
                """
                UPDATE payment_records
                SET razorpay_order_id = %s, status = 'CREATED', attempts = attempts + 1,
                    updated_at = NOW()
                WHERE idempotency_key = %s
                """,
                (razorpay_order_id, idempotency_key),
            )

        _log_payment_action(
            session_id, "PAYMENT_DISPATCH",
            razorpay_order_id=razorpay_order_id,
            amount_paise=request.amount_paise,
            reason=f"Order created: {razorpay_order_id}",
            metadata={"idempotency_key": idempotency_key, "order": order},
        )

        logger.info(
            "Razorpay order created: order_id=%s, session=%s, amount=%d",
            razorpay_order_id, session_id, request.amount_paise,
        )

        # Get the payment_record_id
        with get_db() as conn:
            row = conn.execute(
                "SELECT id FROM payment_records WHERE idempotency_key = %s",
                (idempotency_key,),
            ).fetchone()

        return PaymentDispatchResponse(
            session_id=session_id,
            success=True,
            razorpay_order_id=razorpay_order_id,
            idempotency_key=idempotency_key,
            amount_paise=request.amount_paise,
            currency=request.currency,
            status="CREATED",
            message=f"Order {razorpay_order_id} created successfully.",
            payment_record_id=row["id"] if row else None,
        )

    except razorpay.errors.BadRequestError as e:
        error_msg = str(e)
        # Handle duplicate receipt (idempotent — Razorpay already has this order)
        if "Duplicate request" in error_msg or "same receipt" in error_msg.lower():
            logger.info("Razorpay duplicate receipt detected: %s", idempotency_key)
            _log_payment_action(
                session_id, "PAYMENT_DISPATCH",
                reason=f"Duplicate receipt handled idempotently: {idempotency_key}",
                amount_paise=request.amount_paise,
                metadata={"idempotency_key": idempotency_key, "duplicate": True},
            )
            return PaymentDispatchResponse(
                session_id=session_id,
                success=True,
                idempotency_key=idempotency_key,
                amount_paise=request.amount_paise,
                currency=request.currency,
                status="DUPLICATE",
                message="Idempotent: order already exists on Razorpay.",
            )

        # Explicit simulation mode (must be disabled in production)
        settings = get_settings()
        if settings.payment_simulation_enabled:
            logger.info("Simulated test-mode order for dummy keys: %s", idempotency_key)
            sim_order_id = f"order_sim_{idempotency_key[:16]}"
            with get_db_transaction() as conn:
                conn.execute(
                    """
                    UPDATE payment_records
                    SET razorpay_order_id = %s, status = 'CREATED', attempts = attempts + 1,
                        updated_at = NOW()
                    WHERE idempotency_key = %s
                    """,
                    (sim_order_id, idempotency_key),
                )
            _log_payment_action(
                session_id, "PAYMENT_DISPATCH",
                razorpay_order_id=sim_order_id,
                amount_paise=request.amount_paise,
                reason=f"Simulated test order created: {sim_order_id}",
                metadata={"idempotency_key": idempotency_key, "simulated": True},
            )
            with get_db() as conn:
                row = conn.execute(
                    "SELECT id FROM payment_records WHERE idempotency_key = %s",
                    (idempotency_key,),
                ).fetchone()

            return PaymentDispatchResponse(
                session_id=session_id,
                success=True,
                razorpay_order_id=sim_order_id,
                idempotency_key=idempotency_key,
                amount_paise=request.amount_paise,
                currency=request.currency,
                status="CREATED",
                message=f"Order {sim_order_id} created successfully (test-mode).",
                payment_record_id=row["id"] if row else None,
            )

        logger.error("Razorpay BadRequestError: %s", error_msg)
        with get_db_transaction() as conn:
            conn.execute(
                """
                UPDATE payment_records
                SET status = 'FAILED', last_error = %s, attempts = attempts + 1,
                    updated_at = NOW()
                WHERE idempotency_key = %s
                """,
                (error_msg, idempotency_key),
            )
        _log_payment_action(
            session_id, "PAYMENT_DISPATCH",
            failure_class=FailureClass.NETWORK_FAIL,
            reason=f"Razorpay gateway rejection: {error_msg}",
            amount_paise=request.amount_paise,
            metadata={"idempotency_key": idempotency_key, "error": error_msg},
        )
        return PaymentDispatchResponse(
            session_id=session_id,
            success=False,
            idempotency_key=idempotency_key,
            amount_paise=request.amount_paise,
            currency=request.currency,
            status="FAILED",
            message=f"Payment dispatch rejected by gateway: {error_msg}",
        )

    except Exception as e:
        # Network or unexpected error
        logger.error("Razorpay API error: %s", e)
        with get_db_transaction() as conn:
            conn.execute(
                """
                UPDATE payment_records
                SET status = 'FAILED', last_error = %s, attempts = attempts + 1,
                    updated_at = NOW()
                WHERE idempotency_key = %s
                """,
                (str(e), idempotency_key),
            )

        _log_payment_action(
            session_id, "PAYMENT_DISPATCH",
            failure_class=FailureClass.NETWORK_FAIL,
            reason=f"Razorpay API error: {e}",
            amount_paise=request.amount_paise,
            metadata={"idempotency_key": idempotency_key, "error": str(e)},
        )

        return PaymentDispatchResponse(
            session_id=session_id,
            success=False,
            idempotency_key=idempotency_key,
            amount_paise=request.amount_paise,
            currency=request.currency,
            status="FAILED",
            message=f"Payment dispatch failed: {e}. Will attempt reconciliation.",
        )


def fetch_order_from_razorpay(order_id: str) -> Optional[dict]:
    """
    Fetch order status from Razorpay — THE source of truth.
    Used during reconciliation: never infer failure from our own timeout.
    """
    client = _get_razorpay_client()
    try:
        return client.order.fetch(order_id)
    except Exception as e:
        logger.error("Failed to fetch order %s from Razorpay: %s", order_id, e)
        return None
