"""
End-to-end test suite verifying the interactive simulator flows
matching the exact UI interactions from dashboard/index.html & dashboard/app.js.
"""
import pytest
from fastapi.testclient import TestClient
from src.main import app, _seed_default_catalog
from src.database import init_db
from src.config import get_settings

settings = get_settings()

@pytest.fixture(autouse=True)
def setup_teardown():
    """Setup clean database and catalog seed for simulator tests."""
    init_db()
    _seed_default_catalog()
    yield

@pytest.fixture
def client():
    """Client with trusted host header."""
    return TestClient(app, headers={"host": "localhost"})

def get_auth_headers(client):
    """Helper to authenticate as operator and get Bearer token headers."""
    resp = client.post("/auth/token", data={
        "username": settings.operator_username,
        "password": settings.operator_password,
    })
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


class TestSimulatorFlows:
    """Test suite covering all simulator interactions in the dashboard."""

    def test_preset_1_pass_quantum_pro_and_dispatch(self, client):
        """Preset 1: Buy 1 Quantum X Pro with budget 70000 rupees -> PASS and dispatch payment."""
        session_id = "sim-test-preset-1"
        prompt = "Buy 1 Quantum X Pro with budget 70000 rupees"
        
        # 1. Converse / Guardrail evaluation
        resp = client.post("/checkout/converse", json={
            "session_id": session_id,
            "message": prompt,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["guardrail_decision"] == "PASS"
        assert data["resolved_total_paise"] == 5999900  # ₹59,999
        assert "capability_token" in data
        assert data["capability_token"] is not None

        # 2. Dispatch approved payment
        token = data["capability_token"]
        amount = data["resolved_total_paise"]
        dispatch_resp = client.post("/payment/dispatch", json={
            "session_id": session_id,
            "capability_token": token,
            "amount_paise": amount,
        })
        assert dispatch_resp.status_code == 200
        dispatch_data = dispatch_resp.json()
        assert dispatch_data["success"] is True
        assert dispatch_data["status"] in ("CREATED", "CAPTURED")
        assert dispatch_data["amount_paise"] == amount

    def test_preset_2_pass_soundpods_and_dispatch(self, client):
        """Preset 2: Order 2 SoundPods Pro ANC with budget 12000 rupees -> PASS and dispatch."""
        session_id = "sim-test-preset-2"
        prompt = "Order 2 SoundPods Pro ANC with budget 12000 rupees"
        
        resp = client.post("/checkout/converse", json={
            "session_id": session_id,
            "message": prompt,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["guardrail_decision"] == "PASS"
        assert data["resolved_total_paise"] == 999800  # 2 x ₹4,999 = ₹9,998
        assert data["capability_token"] is not None

        # Dispatch
        dispatch_resp = client.post("/payment/dispatch", json={
            "session_id": session_id,
            "capability_token": data["capability_token"],
            "amount_paise": data["resolved_total_paise"],
        })
        assert dispatch_resp.status_code == 200
        assert dispatch_resp.json()["success"] is True

    def test_preset_3_reject_budget_exceeded(self, client):
        """Preset 3: Buy 1 Quantum X Pro with budget 10000 rupees -> REJECT (Budget Exceeded)."""
        session_id = "sim-test-preset-3"
        prompt = "Buy 1 Quantum X Pro with budget 10000 rupees"
        
        resp = client.post("/checkout/converse", json={
            "session_id": session_id,
            "message": prompt,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["guardrail_decision"] == "REJECT"
        assert "capability_token" not in data or data["capability_token"] is None
        assert "exceeds" in data.get("guardrail_reason", "").lower() or "budget" in data.get("guardrail_reason", "").lower()

    def test_preset_4_multi_item_cart(self, client):
        """Preset 4: Order 1 NeoLite 5G Phone and 1 TurboCharge Charger with budget 25000 rupees."""
        session_id = "sim-test-preset-4"
        prompt = "Order 1 NeoLite 5G Phone and 1 TurboCharge Charger with budget 25000 rupees"
        
        resp = client.post("/checkout/converse", json={
            "session_id": session_id,
            "message": prompt,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["guardrail_decision"] == "PASS"
        # NeoLite (₹19,999) + TurboCharge (₹1,999) = ₹21,998
        assert data["resolved_total_paise"] == 2199800
        assert data["capability_token"] is not None

    def test_operator_auth_and_session_provenance(self, client):
        """Operator authentication and session deep-dive verification."""
        session_id = "sim-test-auth-session"
        # First create an event in that session
        client.post("/checkout/converse", json={
            "session_id": session_id,
            "message": "Buy 1 Quantum X Pro with budget 70000 rupees",
        })
        
        headers = get_auth_headers(client)
        resp = client.get(f"/audit/session/{session_id}", headers=headers)
        assert resp.status_code == 200
        detail = resp.json()
        assert detail["session_id"] == session_id
        assert "audit_trail" in detail
        assert len(detail["audit_trail"]) > 0

    def test_campaign_monte_carlo_run(self, client):
        """Monte Carlo campaign execution simulation."""
        headers = get_auth_headers(client)
        resp = client.post("/campaign/run", headers=headers, json={
            "total_sessions": 20,
            "enable_upsell": True,
        })
        assert resp.status_code == 200
        result = resp.json()
        assert "campaign_id" in result
        assert "conversion_lift_pct" in result
        assert "ci_95_lower" in result
        assert "ci_95_upper" in result

    def test_ledger_reconciliation(self, client):
        """Reconciliation of payment ledgers."""
        headers = get_auth_headers(client)
        resp = client.post("/payment/reconcile-all", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "reconciled" in data
        assert "dead_lettered" in data
        assert "total" in data
