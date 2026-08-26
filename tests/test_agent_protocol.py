"""
Tests for Protocol-Native Agent Endpoints and Stream Tickets.

Verifies:
1. /.well-known/agent.json & /.well-known/ucp discovery manifests
2. /agent/catalog Schema.org JSON-LD generation
3. /agent/checkout programmatic evaluation and capability token minting
4. Single-use SSE stream ticket lifecycle (/auth/stream-ticket)
"""

from __future__ import annotations

import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from src.main import app
from src.database import init_db
from src.catalog.models import CatalogManifest, CatalogItem


@pytest.fixture(autouse=True)
def setup_test_db():
    init_db()
    yield


@pytest.fixture
def client():
    return TestClient(app, headers={"host": "localhost"})


@pytest.fixture
def mock_catalog():
    manifest = CatalogManifest(
        version="1.0.0",
        hash="agent-hash-abc12345",
        items=[
            CatalogItem(
                item_id="watch_001",
                name="PulseBand Smart Watch",
                description="Smart watch",
                price_paise=799900,
                currency="INR",
                available=True,
                stock=50,
                category="wearables",
            ),
        ],
    )
    with patch("src.catalog.service.get_manifest", return_value=manifest):
        yield manifest


def test_agent_discovery_manifest(client, mock_catalog):
    """Verify Universal Commerce Protocol / Agent Discovery manifests."""
    resp1 = client.get("/.well-known/agent.json")
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["@type"] == "AgentServiceDiscovery"
    assert "UAP" in data1["protocol_standards"]
    assert data1["endpoints"]["checkout"] == "/agent/checkout"

    resp2 = client.get("/.well-known/ucp")
    assert resp2.status_code == 200
    assert resp2.json()["name"] == "Agentic Commerce Demo Store"


def test_agent_machine_catalog(client, mock_catalog):
    """Verify machine-readable schema.org JSON-LD catalog."""
    resp = client.get("/agent/catalog")
    assert resp.status_code == 200
    data = resp.json()
    assert data["@type"] == "ItemList"
    assert data["catalog_hash"] == "agent-hash-abc12345"
    assert len(data["itemListElement"]) == 1
    assert data["itemListElement"][0]["sku"] == "watch_001"


def test_agent_programmatic_checkout_pass_and_reject(client, mock_catalog):
    """Verify autonomous agent checkout with capability token minting and budget rejection."""
    # 1. Budget sufficient -> PASS
    pass_resp = client.post(
        "/agent/checkout",
        json={
            "session_id": "agent-test-pass",
            "items": [{"item_id": "watch_001", "quantity": 1}],
            "max_budget_paise": 1000000,  # ₹10,000 > ₹7,999
        },
    )
    assert pass_resp.status_code == 200
    pass_data = pass_resp.json()
    assert pass_data["status"] == "APPROVED"
    assert pass_data["resolved_total_paise"] == 799900
    assert "capability_token" in pass_data

    # 2. Budget insufficient -> REJECT
    reject_resp = client.post(
        "/agent/checkout",
        json={
            "session_id": "agent-test-reject",
            "items": [{"item_id": "watch_001", "quantity": 1}],
            "max_budget_paise": 500000,  # ₹5,000 < ₹7,999
        },
    )
    assert reject_resp.status_code == 200
    reject_data = reject_resp.json()
    assert reject_data["status"] == "REJECTED"
    assert reject_data["failure_class"] == "budget-exceeded"
    assert reject_data["capability_token"] is None


def test_single_use_stream_ticket_lifecycle(client):
    """Verify single-use 30-second stream ticket minting and consumption."""
    # 1. Obtain operator JWT
    auth_resp = client.post(
        "/auth/token",
        data={"username": "admin", "password": "test-operator-password-123"},
    )
    assert auth_resp.status_code == 200
    access_token = auth_resp.json()["access_token"]

    # 2. Mint single-use stream ticket
    ticket_resp = client.post(
        "/auth/stream-ticket",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert ticket_resp.status_code == 200
    data = ticket_resp.json()
    assert "ticket" in data
    assert data["ticket"].startswith("st_")
    assert data["expires_in_seconds"] == 30

    from src.security.auth import validate_and_consume_stream_ticket
    # First consumption succeeds
    assert validate_and_consume_stream_ticket(data["ticket"]) is True
    # Immediate second consumption fails (single-use burned!)
    assert validate_and_consume_stream_ticket(data["ticket"]) is False
