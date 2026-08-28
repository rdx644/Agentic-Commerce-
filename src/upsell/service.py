"""
Bounded upsell agent — offers ONE catalog add-on, re-enters the SAME guardrail.

Design:
- After base cart clears the gate but BEFORE final dispatch
- Query catalog for complementary items (same category/tags, within remaining budget)
- Offer ONE bounded add-on (never multiple — bounded)
- If accepted: build NEW SpendIntent → re-enter SAME guardrail as FRESH check
- NEVER append a charge silently
- If budget insufficient → gracefully skip, log reason
"""

from __future__ import annotations

import json
import logging

from src.catalog import service as catalog_service
from src.guardrail.models import CartItem, Decision, SpendIntent
from src.guardrail import service as guardrail_service
from src.guardrail import ledger as budget_ledger
from src.upsell.models import UpsellAcceptRequest, UpsellOffer, UpsellOfferRequest, UpsellResponse
from src.database import get_db_transaction
from src.security.tokens import verify_capability_token

logger = logging.getLogger(__name__)


def generate_offer(request: UpsellOfferRequest) -> UpsellResponse:
    """
    Generate a bounded upsell offer from the catalog.
    """
    session_id = request.session_id

    token = verify_capability_token(request.capability_token)
    if token is None or token.session_id != session_id:
        return UpsellResponse(
            session_id=session_id,
            message="A valid checkout capability token is required for this session.",
        )

    # Check remaining budget
    state = budget_ledger.get_session_state(session_id)
    if state is None or state.frozen:
        return UpsellResponse(
            session_id=session_id,
            message="No active session or session is frozen.",
        )

    remaining = state.remaining_paise
    if remaining <= 0:
        return UpsellResponse(
            session_id=session_id,
            message="No remaining budget for upsell.",
        )

    # Find candidates from catalog
    candidates = catalog_service.get_upsell_candidates(
        cart_item_ids=request.cart_item_ids,
        max_price_paise=min(remaining, request.remaining_budget_paise),
    )

    if not candidates:
        # Log the skip
        with get_db_transaction() as conn:
            conn.execute(
                """
                INSERT INTO audit_log
                (session_id, action, decision, reason, actor, metadata_json)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    session_id,
                    "UPSELL_OFFER",
                    "REJECT",
                    "No suitable upsell candidates within budget",
                    "agent",
                    json.dumps({
                        "cart_item_ids": request.cart_item_ids,
                        "remaining_budget_paise": remaining,
                    }),
                ),
            )
        return UpsellResponse(
            session_id=session_id,
            message="No suitable add-ons found within your remaining budget.",
        )

    # Pick the best candidate (cheapest that fits)
    best = candidates[0]
    manifest = catalog_service.get_manifest()

    offer = UpsellOffer(
        item_id=best.item_id,
        name=best.name,
        price_paise=best.price_paise,
        reason=f"Complements your {', '.join(request.cart_item_ids)} purchase",
        catalog_version=manifest.version,
        catalog_hash=manifest.hash,
    )

    # Log the offer
    with get_db_transaction() as conn:
        conn.execute(
            """
            INSERT INTO audit_log
            (session_id, action, decision, reason, amount_paise, actor, metadata_json)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                session_id,
                "UPSELL_OFFER",
                "PASS",
                f"Offered: {best.name} at ₹{best.price_paise/100:.2f}",
                best.price_paise,
                "agent",
                json.dumps(offer.model_dump()),
            ),
        )

    return UpsellResponse(
        session_id=session_id,
        offer=offer,
        message=f"How about adding {best.name} for ₹{best.price_paise/100:.2f}?",
    )


def accept_upsell(request: UpsellAcceptRequest) -> UpsellResponse:
    """
    Accept an upsell offer — routes it through the SAME guardrail as a FRESH check.
    Never appends the charge silently.
    """
    session_id = request.session_id
    offer = request.offer
    token = verify_capability_token(request.capability_token)
    if token is None or token.session_id != session_id:
        return UpsellResponse(
            session_id=session_id,
            offer=offer,
            message="A valid checkout capability token is required for this session.",
        )

    manifest = catalog_service.get_manifest()

    # Build a NEW SpendIntent for the upsell — fresh guardrail check
    intent = SpendIntent(
        session_id=session_id,
        items=[CartItem(item_id=offer.item_id, quantity=1)],
        stated_ceiling_paise=offer.price_paise,  # Exact price as ceiling
        catalog_hash=manifest.hash,
        actor="agent",
        intent_type="upsell",
    )

    # Re-enter the SAME guardrail
    decision = guardrail_service.check_spend(intent)

    if decision.decision == Decision.REJECT:
        logger.info(
            "Upsell rejected by guardrail: session=%s, item=%s, reason=%s",
            session_id, offer.item_id, decision.reason,
        )
        return UpsellResponse(
            session_id=session_id,
            offer=offer,
            accepted=False,
            guardrail_decision="REJECT",
            guardrail_reason=decision.reason,
            message=f"Upsell couldn't be added: {decision.reason}",
        )

    logger.info(
        "Upsell accepted and gated: session=%s, item=%s, amount=%d",
        session_id, offer.item_id, offer.price_paise,
    )

    return UpsellResponse(
        session_id=session_id,
        offer=offer,
        accepted=True,
        guardrail_decision="PASS",
        guardrail_reason=decision.reason,
        message=f"✅ {offer.name} added! Separately gated and approved.",
    )
