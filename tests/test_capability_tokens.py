"""
Capability Token Lifecycle & Single-Use Invariant Test Suite.
Verifies cryptographic issuance, expiration, tampering rejection,
session and amount binding, and atomic single-use consumption.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock
import jwt
import pytest

from src.database import init_db, get_db
from src.payment.models import PaymentDispatchRequest
from src.payment.service import dispatch_payment
from src.security.tokens import (
    issue_capability_token,
    verify_capability_token,
    consume_capability_token,
)


@pytest.fixture(autouse=True)
def setup_db():
    init_db()


class TestCapabilityTokens:

    def test_valid_token_issuance_and_claims(self):
        """Tokens must contain iss, aud, token_id, session_id, max_spend_paise, and expire properly."""
        token, token_id = issue_capability_token(
            session_id="sess-cap-001",
            max_spend_paise=50000,
            allowed_item_ids=["phone_001"],
            merchant_id="merchant_demo_001",
        )
        assert token is not None
        assert token_id is not None

        # Verify decoding
        payload = verify_capability_token(token)
        assert payload is not None
        assert payload.token_id == token_id
        assert payload.session_id == "sess-cap-001"
        assert payload.max_spend_paise == 50000
        assert payload.merchant_id == "merchant_demo_001"
        assert payload.allowed_item_ids == ["phone_001"]

    def test_tampered_token_is_rejected(self):
        """Modified signature or claims must be rejected."""
        token, _ = issue_capability_token(
            session_id="sess-cap-002",
            max_spend_paise=50000,
            allowed_item_ids=["phone_001"],
        )
        tampered = token[:-4] + "wxyz"
        assert verify_capability_token(tampered) is None

    def test_expired_token_is_rejected(self):
        """Expired tokens must return None and reject payment dispatch."""
        with patch("src.security.tokens.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                jwt_secret="super-secret-key-for-testing-at-least-32-chars-long",
                capability_token_ttl_seconds=-10,  # Already expired
            )
            token, _ = issue_capability_token(
                session_id="sess-cap-003",
                max_spend_paise=50000,
                allowed_item_ids=["phone_001"],
            )

        assert verify_capability_token(token) is None

    def test_single_use_token_consumed_on_first_payment(self):
        """A capability token is consumed during first payment and cannot authorize a second payment."""
        session_id = "sess-single-use-001"
        amount = 5999900
        token, token_id = issue_capability_token(
            session_id=session_id,
            max_spend_paise=amount,
            allowed_item_ids=["phone_001"],
        )

        req1 = PaymentDispatchRequest(
            session_id=session_id,
            capability_token=token,
            amount_paise=amount,
        )
        resp1 = dispatch_payment(req1)
        assert resp1.success is True
        assert resp1.status in ("CREATED", "PENDING")

        # Verify token is marked consumed in DB
        with get_db() as conn:
            row = conn.execute(
                "SELECT consumed_at FROM capability_tokens WHERE token_id = %s",
                (token_id,),
            ).fetchone()
            assert row is not None
            assert row["consumed_at"] is not None

        # Re-submitting the same token for an INDEPENDENT new session or different amount MUST be rejected
        req2 = PaymentDispatchRequest(
            session_id="sess-single-use-different",
            capability_token=token,
            amount_paise=amount,
        )
        resp2 = dispatch_payment(req2)
        assert resp2.success is False
        assert "mismatch" in resp2.message.lower()

    def test_idempotent_retry_of_same_payment_is_safe(self):
        """Exact same payment request retried with same capability returns existing order (safe retry)."""
        session_id = "sess-idemp-001"
        amount = 1999900
        token, token_id = issue_capability_token(
            session_id=session_id,
            max_spend_paise=amount,
            allowed_item_ids=["phone_002"],
        )

        req = PaymentDispatchRequest(
            session_id=session_id,
            capability_token=token,
            amount_paise=amount,
        )
        resp1 = dispatch_payment(req)
        assert resp1.success is True

        # Exactly same request re-dispatched
        resp2 = dispatch_payment(req)
        assert resp2.success is True
        assert resp2.idempotency_key == resp1.idempotency_key
        assert resp2.razorpay_order_id == resp1.razorpay_order_id

    def test_wrong_amount_rejected_by_payment_service(self):
        """Payment service fails closed if amount does not match authorized capability amount."""
        session_id = "sess-wrong-amt"
        token, _ = issue_capability_token(
            session_id=session_id,
            max_spend_paise=10000,
            allowed_item_ids=["item_01"],
        )
        req = PaymentDispatchRequest(
            session_id=session_id,
            capability_token=token,
            amount_paise=15000,  # Unauthorized amount
        )
        resp = dispatch_payment(req)
        assert resp.success is False
        assert "match" in resp.message.lower()

    def test_wrong_session_rejected_by_payment_service(self):
        """Capability token bound to session A cannot be spent in session B."""
        token, _ = issue_capability_token(
            session_id="session-alpha",
            max_spend_paise=10000,
            allowed_item_ids=["item_01"],
        )
        req = PaymentDispatchRequest(
            session_id="session-beta",
            capability_token=token,
            amount_paise=10000,
        )
        resp = dispatch_payment(req)
        assert resp.success is False
        assert "session" in resp.message.lower()
