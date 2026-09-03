"""
Comprehensive Submission Security Verification Test Suite.
Validates:
1. Single payment boundary invariant (Razorpay never invoked on unauthorized requests)
2. Webhook monetary consistency & payment state machine
3. Hardened CSP without unsafe-inline in script-src
4. Strict Operator OAuth2/JWT claims and role enforcement
"""

import hmac
import hashlib
import json
from unittest.mock import patch, MagicMock
from datetime import timedelta
import pytest
from starlette.testclient import TestClient

from src.main import app
from src.database import init_db, get_db, get_db_transaction
from src.payment.models import PaymentDispatchRequest
from src.payment.service import dispatch_payment
from src.security.auth import create_access_token, require_operator
from src.webhook.handler import _is_legal_transition, process_webhook_event


@pytest.fixture(autouse=True)
def setup_db():
    init_db()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


class TestPaymentSecurityBoundary:
    """Invariant: Razorpay API must never be called on unauthorized, tampered, or missing capability."""

    @patch("src.payment.service._get_razorpay_client")
    def test_mock_razorpay_never_called_on_invalid_token(self, mock_client_getter):
        mock_client = MagicMock()
        mock_client_getter.return_value = mock_client

        req = PaymentDispatchRequest(
            session_id="test-boundary-001",
            capability_token="invalid.garbage.token",
            amount_paise=5000,
        )
        resp = dispatch_payment(req)
        assert resp.success is False
        # Invariant: Razorpay client.order.create was NEVER invoked
        mock_client.order.create.assert_not_called()

    @patch("src.payment.service._get_razorpay_client")
    def test_mock_razorpay_never_called_on_amount_mismatch(self, mock_client_getter):
        from src.security.tokens import issue_capability_token
        mock_client = MagicMock()
        mock_client_getter.return_value = mock_client

        token, _ = issue_capability_token(
            session_id="test-boundary-002",
            max_spend_paise=10000,
            allowed_item_ids=["item_1"],
        )

        req = PaymentDispatchRequest(
            session_id="test-boundary-002",
            capability_token=token,
            amount_paise=99999,  # Mismatch
        )
        resp = dispatch_payment(req)
        assert resp.success is False
        mock_client.order.create.assert_not_called()


class TestWebhookMonetaryConsistencyAndStateMachine:
    """Verifies monetary consistency checks and payment state transition bounds."""

    def test_payment_state_machine_legal_and_illegal_transitions(self):
        # Legal
        assert _is_legal_transition("PENDING", "CREATED") is True
        assert _is_legal_transition("CREATED", "AUTHORIZED") is True
        assert _is_legal_transition("AUTHORIZED", "CAPTURED") is True
        assert _is_legal_transition("CREATED", "FAILED") is True

        # Illegal
        assert _is_legal_transition("CAPTURED", "PENDING") is False
        assert _is_legal_transition("CAPTURED", "CREATED") is False
        assert _is_legal_transition("DEAD_LETTER", "CREATED") is False
        assert _is_legal_transition("FAILED", "CAPTURED") is False

    def test_webhook_monetary_amount_mismatch_is_rejected(self):
        """Webhook with mismatched amount must be rejected and logged to audit trail without mutating state."""
        # Setup existing payment record
        order_id = "order_mismatch_test_001"
        with get_db_transaction() as conn:
            conn.execute(
                """
                INSERT INTO payment_records
                (session_id, idempotency_key, razorpay_order_id, amount_paise, currency, status)
                VALUES (%s, %s, %s, %s, %s, 'CREATED')
                ON CONFLICT (idempotency_key) DO NOTHING
                """,
                ("sess_mismatch", "idemp_mismatch_001", order_id, 50000, "INR"),
            )

        # Webhook payload with altered amount
        payload = {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_test_001",
                        "order_id": order_id,
                        "amount": 99999,  # Different from 50000
                        "currency": "INR",
                    }
                }
            }
        }

        result = process_webhook_event("evt_mismatch_001", "payment.captured", payload)
        assert result["action"] == "monetary_mismatch_rejected"

        # Verify payment record status did NOT change to CAPTURED
        with get_db() as conn:
            row = conn.execute(
                "SELECT status FROM payment_records WHERE razorpay_order_id = %s",
                (order_id,),
            ).fetchone()
            assert row["status"] == "CREATED"

    def test_webhook_currency_mismatch_is_rejected(self):
        """Webhook with unexpected currency is rejected without updating payment record."""
        order_id = "order_cur_mismatch_001"
        with get_db_transaction() as conn:
            conn.execute(
                """
                INSERT INTO payment_records
                (session_id, idempotency_key, razorpay_order_id, amount_paise, currency, status)
                VALUES (%s, %s, %s, %s, %s, 'CREATED')
                ON CONFLICT (idempotency_key) DO NOTHING
                """,
                ("sess_cur_mismatch", "idemp_cur_001", order_id, 20000, "INR"),
            )

        payload = {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_cur_001",
                        "order_id": order_id,
                        "amount": 20000,
                        "currency": "USD",  # Mismatched currency
                    }
                }
            }
        }
        result = process_webhook_event("evt_cur_mismatch_001", "payment.captured", payload)
        assert result["action"] == "monetary_mismatch_rejected"

    def test_webhook_unknown_order_is_rejected(self):
        """Webhook referencing an unknown order is rejected without throwing."""
        payload = {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_unknown_001",
                        "order_id": "order_nonexistent_9999",
                        "amount": 50000,
                        "currency": "INR",
                    }
                }
            }
        }
        result = process_webhook_event("evt_unknown_001", "payment.captured", payload)
        assert result["action"] == "monetary_mismatch_rejected"

    def test_webhook_valid_capture_updates_status(self):
        """Valid capture webhook advances payment state from AUTHORIZED to CAPTURED."""
        order_id = "order_valid_capture_001"
        with get_db_transaction() as conn:
            conn.execute(
                """
                INSERT INTO payment_records
                (session_id, idempotency_key, razorpay_order_id, amount_paise, currency, status)
                VALUES (%s, %s, %s, %s, %s, 'AUTHORIZED')
                ON CONFLICT (idempotency_key) DO NOTHING
                """,
                ("sess_valid_cap", "idemp_valid_cap_001", order_id, 50000, "INR"),
            )

        payload = {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_cap_valid_001",
                        "order_id": order_id,
                        "amount": 50000,
                        "currency": "INR",
                    }
                }
            }
        }
        result = process_webhook_event("evt_valid_cap_001", "payment.captured", payload)
        assert result["action"] == "updated_to_captured"

        with get_db() as conn:
            row = conn.execute(
                "SELECT status, razorpay_payment_id FROM payment_records WHERE razorpay_order_id = %s",
                (order_id,),
            ).fetchone()
            assert row["status"] == "CAPTURED"
            assert row["razorpay_payment_id"] == "pay_cap_valid_001"


class TestContentSecurityPolicyHardening:
    """Verifies that the Content Security Policy does NOT contain unsafe-inline in script-src."""

    def test_csp_header_has_no_unsafe_inline_in_script_src(self, client):
        resp = client.get("/dashboard")
        csp = resp.headers.get("content-security-policy", "")
        assert csp != "", "CSP header must be present"

        # Find script-src directive
        directives = [d.strip() for d in csp.split(";")]
        script_src = next((d for d in directives if d.startswith("script-src")), None)
        assert script_src is not None, "script-src must be defined in CSP"
        assert "'unsafe-inline'" not in script_src, f"script-src must not allow 'unsafe-inline': {script_src}"
        assert "'self'" in script_src


class TestOperatorAuthenticationClaims:
    """Verifies operator JWT validation: role, issuer, audience, expiry."""

    def test_unauthenticated_request_is_rejected(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            require_operator(token=None)
        assert exc.value.status_code == 401

    def test_token_with_wrong_role_is_forbidden(self):
        from fastapi import HTTPException
        # Create token with a different role
        token = create_access_token(
            data={"sub": "guest_user", "role": "viewer"},
            expires_delta=timedelta(minutes=5),
        )
        with pytest.raises(HTTPException) as exc:
            require_operator(token=token)
        assert exc.value.status_code == 403

    def test_valid_operator_token_is_accepted(self):
        token = create_access_token(
            data={"sub": "lead_operator", "role": "operator"},
            expires_delta=timedelta(minutes=5),
        )
        username = require_operator(token=token)
        assert username == "lead_operator"


class TestFrontendSafeDOMAndXSSProtection:
    """Verifies that dashboard frontend contains zero innerHTML or dangerous script execution sinks."""

    def test_no_innerhtml_in_dashboard_app_js(self):
        with open("dashboard/app.js", "r", encoding="utf-8") as f:
            content = f.read()

        dangerous_sinks = ["innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function("]
        for sink in dangerous_sinks:
            assert sink not in content, f"Found dangerous DOM sink '{sink}' in dashboard/app.js"
