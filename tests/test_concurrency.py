"""
High-Concurrency Stress Tests.

Verifies the mathematical correctness and safety of the atomic conditional SQL pattern:
    UPDATE budget_ledger
    SET spent_paise = spent_paise + %s
    WHERE session_id = %s AND frozen = 0 AND spent_paise + %s <= budget_paise

Invariants verified under 100+ concurrent threads:
1. Zero race conditions: Total money authorized NEVER exceeds the stated ceiling under any thread interleaving.
2. Exact boundary enforcement: Exactly floor(budget / chunk) requests pass; all others reject.
3. Webhook Deduplication: 50 concurrent deliveries of the same event_id result in exactly 1 insert.
"""

from __future__ import annotations

import concurrent.futures
import uuid
import pytest

from src.guardrail import ledger as budget_ledger
from src.guardrail import service as guardrail_service
from src.guardrail.models import CartItem, Decision, FailureClass, SpendIntent
from src.catalog.models import CatalogItem, CatalogManifest
from src.webhook import handler as webhook_handler
from src.database import init_db, get_db


@pytest.fixture(autouse=True)
def setup_db():
    init_db()
    yield


def test_concurrent_100_spends_under_fixed_budget():
    """
    STRESS TEST: 100 concurrent threads attempting to spend ₹1,000 against a ₹10,000 budget.
    
    Expected invariant:
    - Exactly 10 requests MUST succeed (10 * ₹1,000 = ₹10,000).
    - Exactly 90 requests MUST be rejected (zero overspend).
    - Final state spent_paise == 1,000,000 paise (₹10,000).
    - Final state spent_paise <= budget_paise.
    """
    session_id = f"concurrency-stress-{uuid.uuid4().hex[:8]}"
    budget_paise = 1000000  # ₹10,000
    spend_per_req_paise = 100000  # ₹1,000

    # Initialize session budget
    budget_ledger.init_session_budget(session_id, budget_paise)

    total_threads = 100
    results: list[bool] = []

    def perform_spend(_):
        return budget_ledger.atomic_spend(session_id, spend_per_req_paise)

    with concurrent.futures.ThreadPoolExecutor(max_workers=25) as executor:
        futures = [executor.submit(perform_spend, i) for i in range(total_threads)]
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())

    success_count = sum(1 for r in results if r is True)
    reject_count = sum(1 for r in results if r is False)

    # Assert exact arithmetic bounds
    assert success_count == 10, f"Expected exactly 10 successes, got {success_count}"
    assert reject_count == 90, f"Expected exactly 90 rejections, got {reject_count}"

    # Verify immutable ledger state
    final_state = budget_ledger.get_session_state(session_id)
    assert final_state is not None
    assert final_state.spent_paise == 1000000
    assert final_state.remaining_paise == 0
    assert final_state.spent_paise <= final_state.budget_paise


def test_concurrent_guardrail_check_spend_enforces_ceiling(monkeypatch):
    """
    50 concurrent guardrail check_spend calls attempting to spend ₹4,999 each
    against a session budget ceiling of ₹20,000.
    
    Expected invariant:
    - Total authorized amount across all passed decisions <= ₹20,000.
    - Exactly 4 requests pass (4 * ₹4,999 = ₹19,996 <= ₹20,000).
    - 46 requests reject with BUDGET_EXCEEDED.
    """
    session_id = f"guardrail-concurrent-{uuid.uuid4().hex[:8]}"
    budget_paise = 2000000  # ₹20,000

    mock_manifest = CatalogManifest(
        version="1.0.0",
        hash="test-catalog-hash-12345",
        items=[
            CatalogItem(
                item_id="earbuds_001",
                name="SoundPods Pro ANC",
                description="Earbuds",
                price_paise=499900,  # ₹4,999
                currency="INR",
                available=True,
                stock=100,
                category="audio",
            ),
        ],
    )
    monkeypatch.setattr("src.catalog.service.get_manifest", lambda: mock_manifest)
    budget_ledger.init_session_budget(session_id, budget_paise)

    def worker(_):
        intent = SpendIntent(
            session_id=session_id,
            items=[CartItem(item_id="earbuds_001", quantity=1)],
            stated_ceiling_paise=budget_paise,
            catalog_hash="test-catalog-hash-12345",
            actor="agent",
            intent_type="checkout",
        )
        return guardrail_service.check_spend(intent)

    total_requests = 50
    decisions: list[guardrail_service.GuardrailDecision] = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(worker, i) for i in range(total_requests)]
        for future in concurrent.futures.as_completed(futures):
            decisions.append(future.result())

    passes = [d for d in decisions if d.decision == Decision.PASS]
    rejects = [d for d in decisions if d.decision == Decision.REJECT]

    total_authorized = sum(d.resolved_total_paise for d in passes)

    assert total_authorized <= budget_paise, f"Total authorized {total_authorized} exceeded budget {budget_paise}"
    assert len(passes) == 4, f"Expected 4 passes, got {len(passes)}"
    assert len(rejects) == 46, f"Expected 46 rejects, got {len(rejects)}"
    assert all(r.failure_class in (FailureClass.BUDGET_EXCEEDED, FailureClass.SESSION_FROZEN) for r in rejects)


def test_concurrent_webhook_deduplication():
    """
    50 concurrent deliveries of the exact same webhook event ID.
    
    Expected invariant:
    - Atomically recorded as new exactly ONCE.
    - Exactly 49 calls are detected as duplicate.
    - Zero duplicate rows in webhook_events.
    """
    event_id = f"evt_concurrent_{uuid.uuid4().hex[:12]}"
    payload = {"event": "payment.authorized", "id": event_id}

    def deliver_webhook(_):
        return webhook_handler.record_and_deduplicate_event(event_id, "payment.authorized", payload)

    results: list[bool] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(deliver_webhook, i) for i in range(50)]
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())

    new_inserts = sum(1 for r in results if r is True)
    duplicates = sum(1 for r in results if r is False)

    assert new_inserts == 1, f"Expected exactly 1 new insert, got {new_inserts}"
    assert duplicates == 49, f"Expected exactly 49 duplicate detections, got {duplicates}"

    with get_db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as count FROM webhook_events WHERE event_id = %s",
            (event_id,),
        ).fetchone()
        assert row["count"] == 1
