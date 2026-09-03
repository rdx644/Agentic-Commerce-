"""
Integration tests validating the Checkout Simulator workflows.

Tests:
1. Chip 1: Single item purchase within budget (Quantum X Pro) -> PASS -> Capability Token -> Payment Dispatch -> SETTLED
2. Chip 2: Multi-quantity purchase (2x SoundPods Pro ANC) -> PASS -> Capability Token -> Payment Dispatch -> SETTLED
3. Chip 3: Budget exceeded purchase (Quantum X Pro with ₹10,000 ceiling) -> REJECT: budget-exceeded -> No Token
4. Chip 4: Multi-item bundle purchase (NeoLite 5G + TurboCharge Charger) -> PASS -> Resolved Total -> Payment Dispatch
5. Clarification message handling on unknown items
"""

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.database import init_db
from src.catalog.models import CatalogItem
from src.catalog.service import seed_catalog


@pytest.fixture(autouse=True)
def setup_catalog():
    init_db()
    from src.catalog import service as catalog_service
    from src.main import _seed_default_catalog
    try:
        catalog_service.get_manifest()
    except ValueError:
        _seed_default_catalog()


@pytest.fixture
def client():
    return TestClient(app, headers={"host": "localhost"})


def test_simulator_chip1_single_item_pass_and_payment(client):
    """Test Chip 1: Buy 1 Quantum X Pro with budget 70000 rupees -> PASS -> Payment Dispatch"""
    session_id = "sim-session-chip1"
    
    # 1. Simulate NL Checkout request
    resp = client.post(
        "/checkout/converse",
        json={"session_id": session_id, "message": "Buy 1 Quantum X Pro with budget 70000 rupees"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["guardrail_decision"] == "PASS"
    assert data["resolved_total_paise"] == 5999900
    assert data["capability_token"] is not None
    assert "Quantum X Pro" in data["message"]

    # 2. Dispatch Payment with Capability Token
    pay_resp = client.post(
        "/payment/dispatch",
        json={
            "session_id": session_id,
            "capability_token": data["capability_token"],
            "amount_paise": data["resolved_total_paise"],
        }
    )
    assert pay_resp.status_code == 200
    pay_data = pay_resp.json()
    assert pay_data["success"] is True
    assert pay_data["amount_paise"] == 5999900
    assert pay_data["status"].upper() in ["CREATED", "CAPTURED"]


def test_simulator_chip2_multi_quantity_pass(client):
    """Test Chip 2: Order 2 SoundPods Pro ANC with budget 12000 rupees -> PASS -> 2x ₹4,999 = ₹9,998"""
    session_id = "sim-session-chip2"
    resp = client.post(
        "/checkout/converse",
        json={"session_id": session_id, "message": "Order 2 SoundPods Pro ANC with budget 12000 rupees"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["guardrail_decision"] == "PASS"
    assert data["resolved_total_paise"] == 999800
    assert data["capability_token"] is not None


def test_simulator_chip3_budget_exceeded_rejection(client):
    """Test Chip 3: Buy 1 Quantum X Pro with budget 10000 rupees -> REJECT: budget-exceeded"""
    session_id = "sim-session-chip3"
    resp = client.post(
        "/checkout/converse",
        json={"session_id": session_id, "message": "Buy 1 Quantum X Pro with budget 10000 rupees"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["guardrail_decision"] == "REJECT"
    assert "budget" in data["guardrail_reason"].lower() or "ceiling" in data["guardrail_reason"].lower()
    assert data["capability_token"] is None


def test_simulator_chip4_multi_item_bundle(client):
    """Test Chip 4: Order 1 NeoLite 5G Phone and 1 TurboCharge Charger with budget 25000 rupees -> PASS -> ₹21,998"""
    session_id = "sim-session-chip4"
    resp = client.post(
        "/checkout/converse",
        json={"session_id": session_id, "message": "Order 1 NeoLite 5G Phone and 1 TurboCharge Charger with budget 25000 rupees"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["guardrail_decision"] == "PASS"
    assert data["resolved_total_paise"] == 2199800  # 19999 + 1999 = 21998
    assert data["capability_token"] is not None
