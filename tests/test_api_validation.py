"""
API Validation Tests — endpoint security, input validation, and response headers.

Tests all API endpoints for:
- Correct rejection of malformed input
- Presence of security headers on all responses
- Health endpoint returns structured status
- Input validation constraints are enforced

Based on backend-development-feature-development skill patterns.
"""

from __future__ import annotations

import json
import pytest
from unittest.mock import patch, MagicMock
from fastapi import HTTPException
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create a test client with mocked database and testserver host allowed."""
    with patch("src.database.init_db"):
        with patch("src.catalog.service.get_manifest") as mock_manifest:
            # Return a minimal manifest to prevent seeding
            mock_manifest.return_value = MagicMock(
                items=[], version="1.0.0", hash="test-hash"
            )
            from src.main import app

            # Add testserver to allowed hosts for testing
            # The test client sends Host: testserver by default
            # We need to patch the middleware config or use the test client
            # with a matching host header
            return TestClient(app, headers={"host": "localhost"})


# ══════════════════════════════════════════════════════════════════════════════
# SECURITY HEADERS
# ══════════════════════════════════════════════════════════════════════════════

class TestSecurityHeaders:
    """Verify security headers are present on all responses."""

    def test_root_has_security_headers(self, client):
        """Root endpoint must include all security headers."""
        response = client.get("/")

        assert response.headers.get("x-content-type-options") == "nosniff"
        assert response.headers.get("x-frame-options") == "DENY"
        assert response.headers.get("x-xss-protection") == "0"
        assert "strict-origin" in response.headers.get("referrer-policy", "")
        # HSTS is sent only for a real HTTPS production deployment. It must not
        # pin local HTTP test/dev hosts to HTTPS.
        assert "strict-transport-security" not in response.headers
        assert "default-src" in response.headers.get("content-security-policy", "")


class TestOperatorAuthentication:
    """Privileged surfaces must have a production-only operator boundary."""

    def test_invalid_operator_credential_is_rejected(self):
        from src.security.auth import require_operator

        settings = MagicMock(
            app_env="production",
            operator_username="operator",
            operator_password="correct-horse-battery-staple",
        )
        with patch("src.security.auth.get_settings", return_value=settings):
            with pytest.raises(HTTPException) as exc:
                require_operator(token="invalid.jwt.token")

        assert exc.value.status_code == 401

    def test_valid_operator_credential_is_accepted(self):
        from src.security.auth import require_operator, create_access_token
        from datetime import timedelta

        settings = MagicMock(
            app_env="production",
            operator_username="operator",
            operator_password="correct-horse-battery-staple",
            jwt_secret="super-secret-key-for-testing-only",
        )
        with patch("src.security.auth.get_settings", return_value=settings):
            # Create a valid token for testing
            valid_token = create_access_token(
                data={"sub": "operator"}, expires_delta=timedelta(minutes=5)
            )
            assert require_operator(token=valid_token) == "operator"

    def test_api_has_no_cache_headers(self, client):
        """API endpoints must have security headers even on errors."""
        response = client.post(
            "/webhook/razorpay",
            content=b'{"event": "payment.captured"}',
            headers={"x-razorpay-signature": "test", "host": "localhost"},
        )
        # Security headers should be on all responses
        assert response.headers.get("x-content-type-options") == "nosniff"


# ══════════════════════════════════════════════════════════════════════════════
# HEALTH ENDPOINT
# ══════════════════════════════════════════════════════════════════════════════

class TestHealthEndpoint:
    """Verify structured health check endpoint."""

    def test_health_returns_structured_response(self, client):
        """Health endpoint must return structured status."""
        with patch("src.database.get_db") as mock_db:
            mock_conn = MagicMock()
            mock_conn.execute.return_value.fetchone.return_value = (1,)
            mock_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_db.return_value.__exit__ = MagicMock(return_value=False)

            response = client.get("/health")
            assert response.status_code == 200

            data = response.json()
            assert "status" in data
            assert "service" in data
            assert "version" in data
            assert "timestamp" in data
            assert "checks" in data
            assert "environment" in data

    def test_health_includes_dependency_checks(self, client):
        """Health must report on database, razorpay, and gemini status."""
        with patch("src.database.get_db") as mock_db:
            mock_conn = MagicMock()
            mock_conn.execute.return_value.fetchone.return_value = (1,)
            mock_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_db.return_value.__exit__ = MagicMock(return_value=False)

            response = client.get("/health")
            data = response.json()

            checks = data["checks"]
            assert "database" in checks
            assert "razorpay_configured" in checks
            assert "gemini_configured" in checks
            assert "webhook_secret_set" in checks


# ══════════════════════════════════════════════════════════════════════════════
# INPUT VALIDATION — CHECKOUT ENDPOINT
# ══════════════════════════════════════════════════════════════════════════════

class TestCheckoutInputValidation:
    """Test input validation on the /checkout/converse endpoint."""

    def test_missing_message_rejected(self, client):
        """Missing required 'message' field must return 422."""
        response = client.post(
            "/checkout/converse",
            json={"session_id": "test"},
        )
        assert response.status_code == 422

    def test_missing_session_id_rejected(self, client):
        """Missing required 'session_id' field must return 422."""
        response = client.post(
            "/checkout/converse",
            json={"message": "Buy a phone"},
        )
        assert response.status_code == 422

    def test_empty_message_rejected(self, client):
        """Empty message must return 422."""
        response = client.post(
            "/checkout/converse",
            json={"message": "", "session_id": "test"},
        )
        assert response.status_code == 422

    def test_oversized_message_rejected(self, client):
        """Message over 2000 chars must return 422."""
        response = client.post(
            "/checkout/converse",
            json={"message": "x" * 2001, "session_id": "test"},
        )
        assert response.status_code == 422

    def test_invalid_session_id_format_rejected(self, client):
        """Session ID with special chars must return 422."""
        response = client.post(
            "/checkout/converse",
            json={
                "message": "Buy a phone",
                "session_id": "'; DROP TABLE audit_log; --",
            },
        )
        assert response.status_code == 422

    def test_oversized_budget_rejected(self, client):
        """Budget over unified MAX_PAYMENT_PAISE (₹10 lakh) must return 422."""
        response = client.post(
            "/checkout/converse",
            json={
                "message": "Buy a phone",
                "session_id": "test",
                "budget_paise": 100_000_001,
            },
        )
        assert response.status_code == 422

    def test_negative_budget_rejected(self, client):
        """Negative budget must return 422."""
        response = client.post(
            "/checkout/converse",
            json={
                "message": "Buy a phone",
                "session_id": "test",
                "budget_paise": -100,
            },
        )
        assert response.status_code == 422

    def test_valid_request_accepted(self, client):
        """Valid request should not return 422 (may return other codes)."""
        with patch("src.checkout.service.process_checkout") as mock_checkout:
            from src.checkout.models import CheckoutResponse
            mock_checkout.return_value = CheckoutResponse(
                session_id="valid-test",
                message="OK",
            )

            response = client.post(
                "/checkout/converse",
                json={
                    "message": "I want to buy the Quantum X Pro",
                    "session_id": "valid-test-session",
                    "budget_paise": 7000000,
                },
            )
            # Should NOT be a validation error
            assert response.status_code != 422


# ══════════════════════════════════════════════════════════════════════════════
# WEBHOOK INPUT VALIDATION
# ══════════════════════════════════════════════════════════════════════════════

class TestWebhookInputValidation:
    """Test input validation on the /webhook/razorpay endpoint."""

    def test_missing_signature_rejected(self, client):
        """Missing signature header must return 400."""
        response = client.post(
            "/webhook/razorpay",
            content=b'{"event": "payment.captured"}',
        )
        assert response.status_code == 400

    def test_invalid_json_rejected(self, client):
        """Invalid JSON body must return 400 (after signature check)."""
        with patch("src.webhook.handler.verify_signature", return_value=True):
            response = client.post(
                "/webhook/razorpay",
                content=b"this is not json",
                headers={"x-razorpay-signature": "test-sig", "host": "localhost"},
            )
            assert response.status_code == 400

    def test_unknown_event_type_ignored(self, client):
        """Unknown event types must be gracefully ignored."""
        with patch("src.webhook.handler.verify_signature", return_value=True):
            response = client.post(
                "/webhook/razorpay",
                content=json.dumps({"event": "unknown.event.type"}).encode(),
                headers={
                    "x-razorpay-signature": "test-sig",
                    "x-razorpay-event-id": "test-event-123",
                    "host": "localhost",
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ignored"
