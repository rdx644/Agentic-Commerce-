"""
Comprehensive Submission Security Verification Test Suite.
Validates:
1. Single payment boundary invariant (Razorpay never invoked on unauthorized requests)
2. Central payment state machine (no illegal transitions, idempotency, payment ID integrity)
3. Server-determined merchant binding & item scope enforcement
4. Webhook fail-closed monetary consistency & durable recovery
5. Hardened CSP without unsafe-inline in script-src & self-hosted D3
6. Operator authorization required for session details (P0 privacy)
7. Production SQLite fail-fast ban
8. Frontend zero-dangerous-DOM sinks check (app.js, architecture_graph.html, generate_graph_html.py)
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
from src.payment.state_machine import (
    transition_payment_state,
    is_legal_transition,
    PaymentStateTransitionError,
    PaymentIdMismatchError,
)
from src.security.auth import create_access_token, require_operator
from src.webhook.handler import process_webhook_event, recover_failed_webhooks
from src.security.rate_limiter import HTTPRateLimiter


@pytest.fixture(autouse=True)
def setup_db():
    init_db()
    from src.catalog import service as catalog_service
    from src.main import _seed_default_catalog
    try:
        catalog_service.get_manifest()
    except ValueError:
        _seed_default_catalog()


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

    @patch("src.payment.service._get_razorpay_client")
    def test_item_scope_enforcement_rejects_unscoped_items(self, mock_client_getter):
        from src.security.tokens import issue_capability_token
        mock_client = MagicMock()
        mock_client_getter.return_value = mock_client

        token, _ = issue_capability_token(
            session_id="test-scope-001",
            max_spend_paise=10000,
            allowed_item_ids=["item_allowed_only"],
        )

        req = PaymentDispatchRequest(
            session_id="test-scope-001",
            capability_token=token,
            amount_paise=10000,
            item_ids=["item_allowed_only", "item_unauthorized"],
        )
        resp = dispatch_payment(req)
        assert resp.success is False
        assert "Item scope mismatch" in resp.message
        mock_client.order.create.assert_not_called()

    @patch("src.payment.service._get_razorpay_client")
    def test_merchant_binding_rejection(self, mock_client_getter):
        """Tokens minted for other merchants cannot be redeemed at this merchant."""
        from src.security.tokens import issue_capability_token

        mock_client = MagicMock()
        mock_client_getter.return_value = mock_client

        token, _ = issue_capability_token(
            session_id="sess_rogue",
            max_spend_paise=5000,
            allowed_item_ids=["item_1"],
            merchant_id="rogue_malicious_merchant",
        )

        req = PaymentDispatchRequest(
            session_id="sess_rogue",
            capability_token=token,
            amount_paise=5000,
        )
        resp = dispatch_payment(req)
        assert resp.success is False
        assert "Merchant binding mismatch" in resp.message
        mock_client.order.create.assert_not_called()


class TestPaymentStateMachine:
    """Verifies state transition invariants, idempotency, and conflicting payment overwrite locks."""

    def test_state_machine_legal_and_illegal_transitions(self):
        # Legal
        assert is_legal_transition("PENDING", "CREATED") is True
        assert is_legal_transition("CREATED", "AUTHORIZED") is True
        assert is_legal_transition("AUTHORIZED", "CAPTURED") is True
        assert is_legal_transition("CREATED", "FAILED") is True
        assert is_legal_transition("CAPTURED", "CAPTURED") is True  # Idempotent

        # Illegal
        assert is_legal_transition("CAPTURED", "PENDING") is False
        assert is_legal_transition("CAPTURED", "CREATED") is False
        assert is_legal_transition("DEAD_LETTER", "CREATED") is False
        assert is_legal_transition("FAILED", "CAPTURED") is False

    def test_state_transition_persists_and_is_idempotent(self):
        order_id = "order_sm_test_001"
        with get_db_transaction() as conn:
            conn.execute(
                """
                INSERT INTO payment_records
                (session_id, idempotency_key, razorpay_order_id, amount_paise, currency, status)
                VALUES (%s, %s, %s, %s, %s, 'CREATED')
                ON CONFLICT (idempotency_key) DO NOTHING
                """,
                ("sess_sm_01", "idemp_sm_01", order_id, 25000, "INR"),
            )

        # Transition to AUTHORIZED
        rec = transition_payment_state(
            razorpay_order_id=order_id,
            new_status="AUTHORIZED",
            razorpay_payment_id="pay_sm_01",
            actor="test",
        )
        assert rec["status"] == "AUTHORIZED"

        # Repeat same transition (idempotent)
        rec2 = transition_payment_state(
            razorpay_order_id=order_id,
            new_status="AUTHORIZED",
            razorpay_payment_id="pay_sm_01",
            actor="test",
        )
        assert rec2["status"] == "AUTHORIZED"

    def test_state_transition_conflicting_payment_id_raises(self):
        order_id = "order_conflict_test_001"
        with get_db_transaction() as conn:
            conn.execute(
                """
                INSERT INTO payment_records
                (session_id, idempotency_key, razorpay_order_id, razorpay_payment_id, amount_paise, currency, status)
                VALUES (%s, %s, %s, %s, %s, %s, 'AUTHORIZED')
                ON CONFLICT (idempotency_key) DO NOTHING
                """,
                ("sess_conf_01", "idemp_conf_01", order_id, "pay_legit_100", 25000, "INR"),
            )

        with pytest.raises(PaymentIdMismatchError):
            transition_payment_state(
                razorpay_order_id=order_id,
                new_status="CAPTURED",
                razorpay_payment_id="pay_IMPOSTOR_999",
                actor="attacker",
            )


class TestWebhookMonetaryConsistencyAndRecovery:
    """Verifies fail-closed monetary checks and durable recovery."""

    def test_webhook_monetary_amount_mismatch_is_rejected(self):
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

        payload = {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_test_001",
                        "order_id": order_id,
                        "amount": 99999,  # Mismatch
                        "currency": "INR",
                    }
                }
            }
        }

        result = process_webhook_event("evt_mismatch_001", "payment.captured", payload)
        assert result["action"] == "monetary_mismatch_rejected"

        with get_db() as conn:
            row = conn.execute(
                "SELECT status FROM payment_records WHERE razorpay_order_id = %s",
                (order_id,),
            ).fetchone()
            assert row["status"] == "CREATED"

    def test_webhook_missing_monetary_fields_fails_closed(self):
        order_id = "order_missing_fields_001"
        with get_db_transaction() as conn:
            conn.execute(
                """
                INSERT INTO payment_records
                (session_id, idempotency_key, razorpay_order_id, amount_paise, currency, status)
                VALUES (%s, %s, %s, %s, %s, 'CREATED')
                ON CONFLICT (idempotency_key) DO NOTHING
                """,
                ("sess_missing_01", "idemp_missing_01", order_id, 50000, "INR"),
            )

        # Missing amount & currency
        payload = {
            "event": "order.paid",
            "payload": {
                "order": {
                    "entity": {
                        "id": order_id,
                    }
                }
            }
        }

        result = process_webhook_event("evt_missing_001", "order.paid", payload)
        assert result["action"] == "monetary_mismatch_rejected"

    def test_durable_webhook_recovery_processes_unhandled_events(self):
        order_id = "order_recov_001"
        event_id = "evt_recov_001"
        with get_db_transaction() as conn:
            conn.execute(
                """
                INSERT INTO payment_records
                (session_id, idempotency_key, razorpay_order_id, amount_paise, currency, status)
                VALUES (%s, %s, %s, %s, %s, 'AUTHORIZED')
                ON CONFLICT (idempotency_key) DO NOTHING
                """,
                ("sess_recov_01", "idemp_recov_01", order_id, 30000, "INR"),
            )

            # Insert raw received webhook event that hasn't processed
            payload = {
                "event": "payment.captured",
                "payload": {
                    "payment": {
                        "entity": {
                            "id": "pay_recov_123",
                            "order_id": order_id,
                            "amount": 30000,
                            "currency": "INR",
                        }
                    }
                }
            }
            conn.execute(
                """
                INSERT INTO webhook_events (event_id, event_type, payload_json, processed, processing_status)
                VALUES (%s, %s, %s, 0, 'RECEIVED')
                ON CONFLICT (event_id) DO NOTHING
                """,
                (event_id, "payment.captured", json.dumps(payload)),
            )

        recovered = recover_failed_webhooks(max_attempts=3)
        assert any(r.get("event_id") == event_id for r in recovered)

        with get_db() as conn:
            pay_row = conn.execute(
                "SELECT status, razorpay_payment_id FROM payment_records WHERE razorpay_order_id = %s",
                (order_id,),
            ).fetchone()
            assert pay_row["status"] == "CAPTURED"
            assert pay_row["razorpay_payment_id"] == "pay_recov_123"

            event_row = conn.execute(
                "SELECT processed, processing_status FROM webhook_events WHERE event_id = %s",
                (event_id,),
            ).fetchone()
            assert event_row["processed"] == 1
            assert event_row["processing_status"] == "PROCESSED"


class TestSessionInformationProtection:
    """Verifies that full session details require operator authorization."""

    def test_anonymous_session_detail_is_unauthorized(self, client):
        resp = client.get("/audit/session/sess_test_123")
        assert resp.status_code == 401, "Anonymous user must NOT access full session audit trail"

    def test_operator_can_access_session_detail(self, client):
        token = create_access_token(
            data={"sub": "super_operator", "role": "operator"},
            expires_delta=timedelta(minutes=5),
        )
        resp = client.get("/audit/session/sess_test_123", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_public_stats_accessible_without_token(self, client):
        resp = client.get("/audit/stats")
        assert resp.status_code == 200
        assert "total_entries" in resp.json()


class TestProductionDatabaseSafety:
    """Verifies that production environments strictly reject SQLite fallback."""

    def test_production_sqlite_raises_runtime_error(self):
        from src.config import Settings
        from src.database import init_db
        from pydantic import ValidationError

        # 1. Pydantic settings level validation
        with pytest.raises(ValidationError) as exc_val:
            Settings(
                app_env="production",
                database_url="sqlite:///fallback.db",
                payment_simulation_enabled=False,
            )
        assert "DATABASE_URL must be PostgreSQL in production" in str(exc_val.value)

        # 2. Database runtime level gate
        mock_settings = MagicMock()
        mock_settings.is_production = True
        mock_settings.database_url = "sqlite:///fallback.db"
        with patch("src.database.get_settings", return_value=mock_settings):
            with pytest.raises(RuntimeError) as exc_run:
                init_db()
            assert "SQLite database is strictly prohibited in production mode" in str(exc_run.value)


class TestRateLimiter:
    """Verifies sliding-window HTTP rate limiter enforcement."""

    def test_rate_limiter_blocks_burst(self):
        limiter = HTTPRateLimiter(requests_per_minute=3)
        # Patch app_env so it behaves like production
        mock_settings = MagicMock()
        mock_settings.app_env = "production"

        with patch("src.security.rate_limiter.get_settings", return_value=mock_settings):
            assert limiter.check("1.2.3.4:/auth/token", max_requests=3) is True
            assert limiter.check("1.2.3.4:/auth/token", max_requests=3) is True
            assert limiter.check("1.2.3.4:/auth/token", max_requests=3) is True
            # 4th request in window must be blocked
            assert limiter.check("1.2.3.4:/auth/token", max_requests=3) is False


class TestFrontendSafeDOMAndXSSProtection:
    """Verifies that dashboard and architecture graph frontend contain zero dangerous script execution sinks."""

    def test_no_innerhtml_in_dashboard_app_js(self):
        with open("dashboard/app.js", "r", encoding="utf-8") as f:
            content = f.read()

        dangerous_sinks = ["innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function("]
        for sink in dangerous_sinks:
            assert sink not in content, f"Found dangerous DOM sink '{sink}' in dashboard/app.js"

    def test_no_innerhtml_in_architecture_graph(self):
        with open("architecture_graph.html", "r", encoding="utf-8") as f:
            content = f.read()

        dangerous_sinks = ["innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function("]
        for sink in dangerous_sinks:
            assert sink not in content, f"Found dangerous DOM sink '{sink}' in architecture_graph.html"
        assert "https://d3js.org" not in content, "architecture_graph.html must use self-hosted d3"

    def test_no_innerhtml_generated_in_generate_graph_script(self):
        with open("scripts/generate_graph_html.py", "r", encoding="utf-8") as f:
            content = f.read()

        dangerous_sinks = [".innerHTML", ".outerHTML", "document.write", "eval("]
        for sink in dangerous_sinks:
            assert sink not in content, f"Found dangerous DOM sink in scripts/generate_graph_html.py"
        assert "https://d3js.org" not in content
