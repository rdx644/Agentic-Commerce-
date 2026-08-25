"""
End-to-End Tests for Checkout Flow.

These tests ensure the integration of parsing, catalog resolution, guardrail,
and payment dispatch works correctly for both successful and rejected scenarios.
"""

from __future__ import annotations

import json
import uuid
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from src.main import app
from src.catalog.models import CatalogManifest, CatalogItem
from src.database import init_db, get_db


@pytest.fixture(autouse=True)
def setup_teardown():
    """Setup and teardown a clean in-memory database for each test."""
    init_db()
    yield


@pytest.fixture
def client():
    """TestClient instance."""
    # Add localhost host header for TrustedHostMiddleware
    return TestClient(app, headers={"host": "localhost"})


@pytest.fixture
def mock_catalog():
    """Mock the catalog to return a known set of items."""
    manifest = CatalogManifest(
        version="1.0.0",
        hash="mock-hash-123",
        items=[
            CatalogItem(
                item_id="phone_001",
                name="Quantum X Pro",
                description="A phone",
                price_paise=5999900,
                currency="INR",
                available=True,
                stock=10,
                category="electronics",
            ),
        ],
    )
    with patch("src.catalog.service.get_manifest", return_value=manifest):
        yield manifest


@pytest.fixture
def mock_gemini():
    """Mock Gemini to return a specific parsed intent."""
    with patch("src.checkout.service.parse_intent") as mock_parse:
        from src.checkout.models import ParsedIntent, ParsedCartItem
        mock_parse.return_value = ParsedIntent(
            items=[ParsedCartItem(item_id="phone_001", quantity=1)],
            ceiling_paise=6000000,
            confidence=0.9,
            clarification_needed=None,
        )
        yield mock_parse


@pytest.fixture
def mock_razorpay():
    """Mock the Razorpay client to return successful order creation."""
    with patch("src.payment.service._get_razorpay_client") as mock_client:
        mock_instance = MagicMock()
        mock_instance.order.create.return_value = {
            "id": "order_mock123",
            "amount": 5999900,
            "currency": "INR",
            "status": "created",
        }
        mock_client.return_value = mock_instance
        yield mock_instance


def test_e2e_happy_path_checkout(client, mock_catalog, mock_gemini, mock_razorpay):
    """
    Test a successful end-to-end checkout flow.
    1. Send NL checkout request
    2. Guardrail should pass
    3. Payment dispatch should create an order
    """
    session_id = f"test-happy-{uuid.uuid4().hex[:8]}"

    # 1. Converse and get approval
    response = client.post(
        "/checkout/converse",
        json={
            "session_id": session_id,
            "message": "I want to buy the Quantum X Pro",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["guardrail_decision"] == "PASS"
    assert "capability_token" in data

    token = data["capability_token"]

    # 2. Dispatch payment
    dispatch_resp = client.post(
        "/payment/dispatch",
        json={
            "session_id": session_id,
            "capability_token": token,
            "amount_paise": 5999900,
        },
    )
    assert dispatch_resp.status_code == 200
    dispatch_data = dispatch_resp.json()
    assert dispatch_data["status"] == "CREATED"
    assert dispatch_data["razorpay_order_id"] == "order_mock123"

    # Verify ledger state
    with get_db() as conn:
        row = conn.execute(
            "SELECT status FROM payment_records WHERE session_id = %s",
            (session_id,)
        ).fetchone()
        assert row["status"] == "CREATED"


def test_e2e_payment_rejects_amount_that_differs_from_capability(
    client, mock_catalog, mock_gemini, mock_razorpay
):
    """A capability authorises one exact order, never a partial/replayed charge."""
    session_id = f"test-exact-amount-{uuid.uuid4().hex[:8]}"
    checkout = client.post(
        "/checkout/converse",
        json={"session_id": session_id, "message": "I want to buy the Quantum X Pro"},
    ).json()

    response = client.post(
        "/payment/dispatch",
        json={
            "session_id": session_id,
            "capability_token": checkout["capability_token"],
            "amount_paise": 1,
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    mock_razorpay.order.create.assert_not_called()


def test_e2e_rejection_path_budget_exceeded(client, mock_catalog):
    """
    Test rejection when LLM/user budget is less than catalog price.
    """
    session_id = f"test-reject-{uuid.uuid4().hex[:8]}"

    # Mock Gemini to return a ceiling lower than the catalog price
    with patch("src.checkout.service.parse_intent") as mock_parse:
        from src.checkout.models import ParsedIntent, ParsedCartItem
        mock_parse.return_value = ParsedIntent(
            items=[ParsedCartItem(item_id="phone_001", quantity=1)],
            ceiling_paise=5000000,  # 50k vs catalog price 59.9k
            confidence=0.9,
            clarification_needed=None,
        )

        response = client.post(
            "/checkout/converse",
            json={
                "session_id": session_id,
                "message": "I want to buy the Quantum X Pro for under 50k",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["guardrail_decision"] == "REJECT"
    assert "exceeds stated ceiling" in data["guardrail_reason"].lower()
    assert data.get("capability_token") is None

    # Verify attempting dispatch without a token fails (validation)
    dispatch_resp = client.post(
        "/payment/dispatch",
        json={
            "session_id": session_id,
            "amount_paise": 5999900,
        },
    )
    assert dispatch_resp.status_code == 422  # Missing capability_token

    # Verify attempting dispatch with a fake token fails
    dispatch_resp_fake = client.post(
        "/payment/dispatch",
        json={
            "session_id": session_id,
            "capability_token": "fake-token-123",
            "amount_paise": 5999900,
        },
    )
    assert dispatch_resp_fake.status_code == 200
    fake_data = dispatch_resp_fake.json()
    assert fake_data["success"] is False
    assert fake_data["status"] == "REJECTED"
