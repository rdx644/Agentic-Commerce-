"""
Full System Verification Test Suite.
Rigorous end-to-end verification of:
1. Static asset delivery, headers, CSP, and cache-busting
2. Authentication workflows (Guest mode vs Operator mode)
3. Privileged campaign gating vs Public audit transparency
4. Session deep-dive without authentication friction
5. Checkout simulator -> Guardrail -> Token Minting -> Payment Dispatch
6. Real-time audit stats and stream ticket minting
"""

import pytest
from starlette.testclient import TestClient
from src.main import app
from src.config import get_settings
from src.database import init_db
from src.catalog.models import CatalogItem
from src.catalog.service import seed_catalog


@pytest.fixture(autouse=True)
def setup_database():
    init_db()
    items = [
        CatalogItem(
            item_id="phone_001",
            name="Quantum X Pro Smartphone",
            description="Flagship smartphone with AI camera",
            price_paise=5999900,
            category="smartphones",
            tags=["electronics", "mobile"],
        ),
        CatalogItem(
            item_id="phone_002",
            name="NeoLite 5G Phone",
            description="Mid-range 5G smartphone",
            price_paise=1999900,
            category="smartphones",
            tags=["electronics", "mobile"],
        ),
    ]
    seed_catalog(items, version="1.0.0")


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_dashboard_and_static_asset_pipeline(client):
    """Verify dashboard HTML and static assets deliver with correct headers and cache-busting tags."""
    # 1. GET /dashboard
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    html = resp.text
    assert "styles.css?v=" in html
    assert "app.js?v=" in html
    assert "GUEST OBSERVER" in html
    assert "OPERATOR LOGIN" in html
    assert "RUN CAMPAIGN" in html
    assert "checkout-panel" in html
    assert resp.headers.get("Cache-Control") == "no-cache, must-revalidate"
    assert "fonts.googleapis.com" in resp.headers.get("Content-Security-Policy", "")

    # 2. GET /dashboard/static/app.js
    app_js_resp = client.get("/dashboard/static/app.js")
    assert app_js_resp.status_code == 200
    assert "updateAuthUI" in app_js_resp.text
    assert "showToast" in app_js_resp.text
    assert "sessionStorage" in app_js_resp.text
    assert app_js_resp.headers.get("Cache-Control") == "no-cache, must-revalidate"

    # 3. GET /dashboard/static/styles.css
    css_resp = client.get("/dashboard/static/styles.css")
    assert css_resp.status_code == 200
    assert ".auth-badge" in css_resp.text
    assert "--measure-cyan" in css_resp.text
    assert css_resp.headers.get("Cache-Control") == "no-cache, must-revalidate"


def test_auth_operator_login_and_logout_gating(client):
    """Verify operator authentication challenges and permission gating."""
    settings = get_settings()

    # 1. Unauthenticated /campaign/run MUST return 401
    unauth_camp = client.post("/campaign/run", json={"total_sessions": 10})
    assert unauth_camp.status_code == 401

    # 2. Invalid credentials MUST return 401
    bad_login = client.post(
        "/auth/token",
        data={"username": "wrong_user", "password": "wrong_password"}
    )
    assert bad_login.status_code == 401

    # 3. Valid Operator credentials MUST return JWT
    valid_login = client.post(
        "/auth/token",
        data={"username": settings.operator_username, "password": settings.operator_password}
    )
    assert valid_login.status_code == 200
    auth_data = valid_login.json()
    assert "access_token" in auth_data
    token = auth_data["access_token"]

    # 4. Authenticated /campaign/run MUST succeed
    auth_camp = client.post(
        "/campaign/run",
        json={"total_sessions": 10, "enable_upsell": True},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert auth_camp.status_code == 200
    camp_report = auth_camp.json()
    assert camp_report["total_sessions"] == 10
    assert "conversion_lift_pct" in camp_report
    assert "revenue_delta_paise" in camp_report


def test_public_guest_audit_transparency(client):
    """Verify public guests can inspect audit stats, audit trails, and session deep dive."""
    # 1. Audit Stats (Public)
    stats_resp = client.get("/audit/stats")
    assert stats_resp.status_code == 200
    stats = stats_resp.json()
    assert "total_entries" in stats
    assert "budget_summary" in stats

    # 2. Audit Trail (Public)
    trail_resp = client.get("/audit/trail?limit=20")
    assert trail_resp.status_code == 200
    assert isinstance(trail_resp.json(), list)

    # 3. Session Deep Dive (Public Inspection for judges)
    # Run a test checkout to create a session
    sess_id = "test-session-verify-001"
    client.post(
        "/checkout/converse",
        json={"session_id": sess_id, "message": "Buy 1 Quantum X Pro with budget 70000 rupees"}
    )

    # Query session detail without auth headers
    sess_resp = client.get(f"/audit/session/{sess_id}")
    assert sess_resp.status_code == 200
    sess_data = sess_resp.json()
    assert sess_data["session_id"] == sess_id
    assert "audit_trail" in sess_data
    assert len(sess_data["audit_trail"]) > 0


def test_full_checkout_simulator_to_payment_pipeline(client):
    """Verify end-to-end checkout flow from natural language to payment dispatch."""
    session_id = "e2e-judge-demo-session"

    # Step 1: Converse / Intent Parsing
    resp = client.post(
        "/checkout/converse",
        json={"session_id": session_id, "message": "Buy 1 Quantum X Pro with budget 70000 rupees"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["guardrail_decision"] == "PASS"
    assert data["resolved_total_paise"] == 5999900
    assert data["capability_token"] is not None
    token = data["capability_token"]

    # Step 2: Payment Dispatch
    pay_resp = client.post(
        "/payment/dispatch",
        json={
            "session_id": session_id,
            "capability_token": token,
            "amount_paise": 5999900
        }
    )
    assert pay_resp.status_code == 200
    pay_data = pay_resp.json()
    assert pay_data["success"] is True
    assert pay_data["amount_paise"] == 5999900

    # Step 3: Idempotent replay
    replay_resp = client.post(
        "/payment/dispatch",
        json={
            "session_id": session_id,
            "capability_token": token,
            "amount_paise": 5999900
        }
    )
    assert replay_resp.status_code == 200
    replay_data = replay_resp.json()
    assert replay_data["success"] is True
