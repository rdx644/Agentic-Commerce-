"""
Guardrail service — THE discrete checkpoint between "agent wants to spend" and "money moves."

This is the system's differentiator. Every spend goes through here. The flow:
1. Check session not frozen (rate-limit)
2. Price-drift check: every item price verified against catalog at the quoted hash
3. Budget ceiling check: total ≤ stated ceiling
4. Atomic budget write: single conditional UPDATE
5. Capability token issuance: on PASS, issue short-TTL JWT
6. Decision logging: log PASS or REJECT to audit_log BEFORE any Razorpay call

Invariants:
- The LLM's output is never wired directly to the payment call.
- A prompt instruction is not a bound — a hard numeric check is.
- Guardrail rejection is NEVER retried downstream.
"""

from __future__ import annotations

import json
import logging

from src.catalog import service as catalog_service
from src.catalog.models import CatalogItem
from src.guardrail.models import (
    CartItem,
    Decision,
    FailureClass,
    GuardrailCheck,
    GuardrailDecision,
    SpendIntent,
)
from src.guardrail import ledger as budget_ledger
from src.security.tokens import issue_capability_token
from src.security.rate_limiter import check_and_freeze_if_needed
from src.database import get_db_transaction

logger = logging.getLogger(__name__)


def _log_decision(decision: GuardrailDecision, intent: SpendIntent) -> None:
    """
    Log the guardrail decision to the audit trail BEFORE any Razorpay call.
    This is a real table row, not an app log.
    """
    with get_db_transaction() as conn:
        conn.execute(
            """
            INSERT INTO audit_log
            (session_id, action, decision, failure_class, reason, amount_paise,
             catalog_version, catalog_hash, actor, capability_token_id, metadata_json)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                decision.session_id,
                "GUARDRAIL_CHECK",
                decision.decision.value,
                decision.failure_class.value if decision.failure_class else None,
                decision.reason,
                decision.resolved_total_paise,
                decision.catalog_version,
                decision.catalog_hash,
                intent.actor,
                decision.capability_token_id,
                json.dumps({
                    "intent_type": intent.intent_type,
                    "items": [item.model_dump() for item in intent.items],
                    "stated_ceiling_paise": intent.stated_ceiling_paise,
                    "checks": [c.model_dump() for c in decision.checks_performed],
                }),
            ),
        )


def check_spend(intent: SpendIntent) -> GuardrailDecision:
    """
    Main guardrail entry point. Runs all checks and returns a decision.
    Decision is logged to audit trail before returning.
    """
    checks: list[GuardrailCheck] = []
    session_id = intent.session_id

    # ── Check 1: Session not frozen ───────────────────────────────────────
    if check_and_freeze_if_needed(session_id):
        decision = GuardrailDecision(
            decision=Decision.REJECT,
            session_id=session_id,
            checks_performed=[GuardrailCheck(
                check_name="session_freeze",
                passed=False,
                detail="Session frozen after too many consecutive rejections",
            )],
            reason="Session frozen — too many consecutive guardrail rejections",
            failure_class=FailureClass.SESSION_FROZEN,
        )
        _log_decision(decision, intent)
        return decision

    checks.append(GuardrailCheck(
        check_name="session_freeze",
        passed=True,
        detail="Session is active",
    ))

    # ── Check 2: All items exist and are available ────────────────────────
    manifest = catalog_service.get_manifest()
    item_map = {item.item_id: item for item in manifest.items}
    resolved_items: list[tuple[CartItem, CatalogItem]] = []

    for cart_item in intent.items:
        catalog_item = item_map.get(cart_item.item_id)
        if catalog_item is None or not catalog_item.available:
            decision = GuardrailDecision(
                decision=Decision.REJECT,
                session_id=session_id,
                checks_performed=checks + [GuardrailCheck(
                    check_name="item_availability",
                    passed=False,
                    detail=f"Item '{cart_item.item_id}' not found or unavailable",
                )],
                reason=f"Item '{cart_item.item_id}' not found or unavailable in catalog",
                failure_class=FailureClass.ITEM_UNAVAILABLE,
                catalog_version=manifest.version,
                catalog_hash=manifest.hash,
            )
            _log_decision(decision, intent)
            return decision
        resolved_items.append((cart_item, catalog_item))

    checks.append(GuardrailCheck(
        check_name="item_availability",
        passed=True,
        detail=f"All {len(intent.items)} items found and available",
    ))

    # ── Check 3: Price drift against catalog hash ─────────────────────────
    for cart_item, catalog_item in resolved_items:
        drift_result = catalog_service.check_price_drift(
            item_id=cart_item.item_id,
            quoted_price_paise=catalog_item.price_paise,  # current price
            quoted_catalog_hash=intent.catalog_hash,
        )
        if not drift_result.match:
            decision = GuardrailDecision(
                decision=Decision.REJECT,
                session_id=session_id,
                checks_performed=checks + [GuardrailCheck(
                    check_name="price_drift",
                    passed=False,
                    detail=(
                        f"Price drift on '{cart_item.item_id}': "
                        f"quoted hash={intent.catalog_hash[:12]}... "
                        f"current hash={manifest.hash[:12]}... "
                        f"drift={drift_result.drift_paise} paise"
                    ),
                )],
                reason="Catalog changed since quote (hash mismatch). Re-fetch catalog and retry.",
                failure_class=FailureClass.PRICE_DRIFT,
                catalog_version=manifest.version,
                catalog_hash=manifest.hash,
            )
            _log_decision(decision, intent)
            return decision

    checks.append(GuardrailCheck(
        check_name="price_drift",
        passed=True,
        detail=f"All prices match catalog hash {manifest.hash[:12]}...",
    ))

    # ── Check 4: Compute total from catalog (not LLM) ────────────────────
    total_paise = sum(
        catalog_item.price_paise * cart_item.quantity
        for cart_item, catalog_item in resolved_items
    )

    # ── Check 5: Total ≤ stated ceiling ───────────────────────────────────
    if total_paise > intent.stated_ceiling_paise:
        decision = GuardrailDecision(
            decision=Decision.REJECT,
            session_id=session_id,
            checks_performed=checks + [GuardrailCheck(
                check_name="ceiling_check",
                passed=False,
                detail=f"Total {total_paise} paise > ceiling {intent.stated_ceiling_paise} paise",
            )],
            reason=f"Cart total (₹{total_paise/100:,.0f}) exceeds stated ceiling (₹{intent.stated_ceiling_paise/100:,.0f})",
            failure_class=FailureClass.BUDGET_EXCEEDED,
            resolved_total_paise=total_paise,
            catalog_version=manifest.version,
            catalog_hash=manifest.hash,
        )
        _log_decision(decision, intent)
        return decision

    checks.append(GuardrailCheck(
        check_name="ceiling_check",
        passed=True,
        detail=f"Total {total_paise} paise ≤ ceiling {intent.stated_ceiling_paise} paise",
    ))

    # ── Check 6: Atomic budget write ──────────────────────────────────────
    # Ensure session has a budget entry
    state = budget_ledger.get_session_state(session_id)
    if state is None:
        budget_ledger.init_session_budget(session_id, intent.stated_ceiling_paise)

    budget_ok = budget_ledger.atomic_spend(session_id, total_paise)
    if not budget_ok:
        # Check if should freeze after this rejection
        check_and_freeze_if_needed(session_id)

        decision = GuardrailDecision(
            decision=Decision.REJECT,
            session_id=session_id,
            checks_performed=checks + [GuardrailCheck(
                check_name="atomic_budget",
                passed=False,
                detail=f"Atomic spend of {total_paise} paise rejected by ledger",
            )],
            reason="Budget exceeded or session frozen. Remaining budget insufficient.",
            failure_class=FailureClass.BUDGET_EXCEEDED,
            resolved_total_paise=total_paise,
            catalog_version=manifest.version,
            catalog_hash=manifest.hash,
        )
        _log_decision(decision, intent)
        return decision

    checks.append(GuardrailCheck(
        check_name="atomic_budget",
        passed=True,
        detail=f"Atomic spend of {total_paise} paise accepted",
    ))

    # ── All checks passed — issue capability token ────────────────────────
    allowed_item_ids = [ci.item_id for ci in intent.items]
    token, token_id = issue_capability_token(
        session_id=session_id,
        max_spend_paise=total_paise,
        allowed_item_ids=allowed_item_ids,
    )

    decision = GuardrailDecision(
        decision=Decision.PASS,
        session_id=session_id,
        checks_performed=checks,
        reason=f"All checks passed. Total: ₹{total_paise/100:,.0f}. Capability token issued.",
        resolved_total_paise=total_paise,
        catalog_version=manifest.version,
        catalog_hash=manifest.hash,
        capability_token=token,
        capability_token_id=token_id,
    )

    # Log BEFORE any Razorpay call
    _log_decision(decision, intent)
    logger.info(
        "Guardrail PASS: session=%s, total=%d paise, token=%s",
        session_id,
        total_paise,
        token_id[:8],
    )
    return decision
