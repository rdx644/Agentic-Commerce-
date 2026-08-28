"""
Checkout service — orchestrates parse → validate → guardrail → dispatch.

Flow:
1. Gemini parses NL → structured intent (item_ids + ceiling)
2. Resolve each item_id against catalog (deterministic — prices from catalog, not LLM)
3. Build SpendIntent with catalog hash
4. Feed into guardrail
5. If PASS → return capability token for downstream payment dispatch
6. If REJECT → return rejection reason (never retry a guardrail rejection)
"""

from __future__ import annotations

import logging

from src.catalog import service as catalog_service
from src.checkout.llm import parse_intent
from src.checkout.models import CheckoutRequest, CheckoutResponse
from src.guardrail.models import CartItem, Decision, SpendIntent
from src.guardrail import service as guardrail_service

logger = logging.getLogger(__name__)


def process_checkout(request: CheckoutRequest) -> CheckoutResponse:
    """
    Full checkout pipeline: NL → intent → guardrail → response.
    """
    session_id = request.session_id

    # ── Step 1: Parse NL to structured intent ─────────────────────────────
    try:
        parsed = parse_intent(request.message)
    except ValueError as e:
        return CheckoutResponse(
            session_id=session_id,
            message=f"I couldn't understand your request: {e}",
        )

    # Handle clarification needed
    if parsed.clarification_needed:
        return CheckoutResponse(
            session_id=session_id,
            message=parsed.clarification_needed,
            parsed_intent=parsed,
        )

    if not parsed.items:
        return CheckoutResponse(
            session_id=session_id,
            message="I couldn't identify any items in your request. Could you specify which products you'd like?",
            parsed_intent=parsed,
        )

    # ── Step 2: Resolve against catalog (deterministic) ───────────────────
    manifest = catalog_service.get_manifest()
    item_map = {item.item_id: item for item in manifest.items}

    cart_items: list[CartItem] = []
    item_names: list[str] = []

    for parsed_item in parsed.items:
        catalog_item = item_map.get(parsed_item.item_id)
        if catalog_item is None or not catalog_item.available:
            return CheckoutResponse(
                session_id=session_id,
                message=f"Sorry, '{parsed_item.item_id}' is not available. Please check our catalog.",
                parsed_intent=parsed,
                catalog_version=manifest.version,
                catalog_hash=manifest.hash,
            )

        cart_items.append(CartItem(
            item_id=parsed_item.item_id,
            quantity=parsed_item.quantity,
            resolved_price_paise=catalog_item.price_paise,
        ))
        item_names.append(f"{catalog_item.name} x{parsed_item.quantity}")

    # Use explicit budget if provided, otherwise use LLM-parsed ceiling
    ceiling = request.budget_paise or parsed.ceiling_paise

    # ── Step 3: Build SpendIntent with catalog hash ───────────────────────
    intent = SpendIntent(
        session_id=session_id,
        items=cart_items,
        stated_ceiling_paise=ceiling,
        catalog_hash=manifest.hash,
        actor="user",
        intent_type="checkout",
    )

    # ── Step 4: Feed into guardrail ───────────────────────────────────────
    decision = guardrail_service.check_spend(intent)

    if decision.decision == Decision.REJECT:
        return CheckoutResponse(
            session_id=session_id,
            message=f"Checkout blocked: {decision.reason}",
            parsed_intent=parsed,
            guardrail_decision="REJECT",
            guardrail_reason=decision.reason,
            resolved_total_paise=decision.resolved_total_paise,
            catalog_version=decision.catalog_version,
            catalog_hash=decision.catalog_hash,
        )

    # ── Step 5: PASS — return with capability token ───────────────────────
    items_summary = ", ".join(item_names)
    total_rupees = decision.resolved_total_paise / 100

    return CheckoutResponse(
        session_id=session_id,
        message=(
            f"✅ Checkout approved! Cart: {items_summary}. "
            f"Total: ₹{total_rupees:.2f}. "
            f"A capability token has been issued for payment dispatch."
        ),
        parsed_intent=parsed,
        guardrail_decision="PASS",
        guardrail_reason=decision.reason,
        resolved_total_paise=decision.resolved_total_paise,
        capability_token=decision.capability_token,
        catalog_version=decision.catalog_version,
        catalog_hash=decision.catalog_hash,
    )
