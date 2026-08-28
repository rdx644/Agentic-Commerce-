"""
Protocol-Native Agent Interface (AI Buyer & Agent-to-Agent Commerce).

Implements open agent protocol standards (NPCI UAP, ACP, AP2, x402, UCP):
- /.well-known/agent.json & /.well-known/ucp (Universal Commerce Protocol discovery)
- /agent/catalog (Schema.org / JSON-LD machine-readable catalog)
- /agent/checkout (Programmatic structured agent checkout)
- /agent/authorize (Cryptographic capability token authorization)
- /agent/payment (Autonomous agent token settlement)
"""

from __future__ import annotations

import logging
import uuid
from typing import List, Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, status

from src.catalog import service as catalog_service
from src.guardrail import service as guardrail_service
from src.guardrail.models import CartItem, Decision, SpendIntent
from src.payment import service as payment_service
from src.payment.models import PaymentDispatchRequest
from src.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Agent Protocol"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class AgentItemRequest(BaseModel):
    item_id: str
    quantity: int = Field(default=1, ge=1, le=100)


class AgentCheckoutRequest(BaseModel):
    session_id: Optional[str] = None
    items: List[AgentItemRequest]
    max_budget_paise: int = Field(description="Strict spending ceiling in paise (₹1 = 100 paise)")
    catalog_hash: Optional[str] = None
    agent_identity: Optional[str] = "autonomous_ai_buyer"


class AgentAuthorizeRequest(BaseModel):
    session_id: str
    items: List[AgentItemRequest]
    max_budget_paise: int


class AgentPaymentRequest(BaseModel):
    session_id: str
    capability_token: str
    amount_paise: int


# ── Discovery Endpoints ───────────────────────────────────────────────────────

@router.get("/.well-known/agent.json", summary="Agent Discovery Manifest")
async def get_agent_manifest():
    """
    Machine-readable discovery manifest for autonomous AI buyers.
    Defines supported protocol versions, bounded spend guardrails, and cryptographic token specs.
    """
    settings = get_settings()
    try:
        manifest = catalog_service.get_manifest()
        cat_ver = manifest.version
        cat_hash = manifest.hash
    except Exception:
        cat_ver = "1.0.0"
        cat_hash = "unseeded"

    return {
        "@context": "https://schema.org",
        "@type": "AgentServiceDiscovery",
        "service": "Agentic Commerce Platform",
        "protocol_standards": ["UAP", "ACP", "AP2", "x402", "UCP"],
        "version": "1.0.0",
        "merchant": {
            "name": "Quantum Electronics Merchant",
            "settlement_rail": "Razorpay Test Mode",
            "currency": "INR",
        },
        "catalog_state": {
            "version": cat_ver,
            "hash": cat_hash,
            "manifest_url": "/agent/catalog",
        },
        "endpoints": {
            "discovery": "/.well-known/agent.json",
            "catalog": "/agent/catalog",
            "checkout": "/agent/checkout",
            "authorize": "/agent/authorize",
            "payment": "/agent/payment",
        },
        "guardrail_spec": {
            "enforcement": "strict_bounded_numeric",
            "capability_token_ttl_seconds": settings.capability_token_ttl_seconds,
            "max_consecutive_rejections": settings.max_consecutive_rejections,
            "audit_trail": "sha256_chained",
        },
    }


# ── Machine-Readable Catalog ──────────────────────────────────────────────────

@router.get("/agent/catalog", summary="Machine-Readable Agent Catalog (JSON-LD)")
async def get_agent_catalog():
    """
    Schema.org / JSON-LD machine-readable product catalog.
    Enables AI agents to semantically discover items, current stock, and cryptographic integrity hashes.
    """
    manifest = catalog_service.get_manifest()

    item_elements = [
        {
            "@type": "Product",
            "sku": item.item_id,
            "name": item.name,
            "description": item.description,
            "category": item.category,
            "offers": {
                "@type": "Offer",
                "price": item.price_paise / 100,
                "priceCurrency": "INR",
                "priceSpecification": {
                    "price_paise": item.price_paise,
                    "currency": "INR",
                },
                "availability": "https://schema.org/InStock" if item.available else "https://schema.org/OutOfStock",
            },
            "tags": item.tags,
        }
        for item in manifest.items
        if item.available
    ]

    return {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "catalog_version": manifest.version,
        "catalog_hash": manifest.hash,
        "total_items": len(item_elements),
        "itemListElement": item_elements,
    }


# ── Programmatic Agent Checkout ───────────────────────────────────────────────

@router.post("/agent/checkout", summary="Autonomous Agent Checkout")
async def agent_checkout(req: AgentCheckoutRequest):
    """
    Structured checkout interface for AI buyers.
    Evaluates requested items and spending ceiling directly through deterministic guardrails.
    Returns a short-lived cryptographic Capability Token on approval.
    """
    session_id = req.session_id or f"agent_sess_{uuid.uuid4().hex[:10]}"
    manifest = catalog_service.get_manifest()
    catalog_hash = req.catalog_hash or manifest.hash

    cart_items = [CartItem(item_id=it.item_id, quantity=it.quantity) for it in req.items]

    intent = SpendIntent(
        session_id=session_id,
        items=cart_items,
        stated_ceiling_paise=req.max_budget_paise,
        catalog_hash=catalog_hash,
        actor=req.agent_identity or "autonomous_ai_buyer",
        intent_type="agent_checkout",
    )

    decision = guardrail_service.check_spend(intent)

    if decision.decision != Decision.PASS:
        return {
            "status": "REJECTED",
            "session_id": session_id,
            "decision": decision.decision.value,
            "failure_class": decision.failure_class.value if decision.failure_class else "UNKNOWN",
            "reason": decision.reason,
            "resolved_total_paise": decision.resolved_total_paise,
            "catalog_hash": decision.catalog_hash,
            "capability_token": None,
        }

    return {
        "status": "APPROVED",
        "session_id": session_id,
        "decision": decision.decision.value,
        "reason": decision.reason,
        "resolved_total_paise": decision.resolved_total_paise,
        "catalog_hash": decision.catalog_hash,
        "capability_token": decision.capability_token,
        "ttl_seconds": 300,
        "next_step": {
            "endpoint": "/agent/payment",
            "method": "POST",
            "payload_format": {
                "session_id": session_id,
                "capability_token": decision.capability_token,
                "amount_paise": decision.resolved_total_paise,
            },
        },
    }


# ── Agent Capability Token Authorization ──────────────────────────────────────

@router.post("/agent/authorize", summary="Mint Agent Capability Token")
async def agent_authorize(req: AgentAuthorizeRequest):
    """
    Directly mints a signed capability token for an agent session after guardrail checks.
    """
    manifest = catalog_service.get_manifest()
    cart_items = [CartItem(item_id=it.item_id, quantity=it.quantity) for it in req.items]

    intent = SpendIntent(
        session_id=req.session_id,
        items=cart_items,
        stated_ceiling_paise=req.max_budget_paise,
        catalog_hash=manifest.hash,
        actor="autonomous_ai_buyer",
        intent_type="agent_authorize",
    )

    decision = guardrail_service.check_spend(intent)

    if decision.decision != Decision.PASS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"reason": decision.reason, "failure_class": decision.failure_class.value if decision.failure_class else None},
        )

    return {
        "status": "AUTHORIZED",
        "session_id": req.session_id,
        "capability_token": decision.capability_token,
        "token_id": decision.capability_token_id,
        "authorized_amount_paise": decision.resolved_total_paise,
        "expires_in_seconds": 300,
    }


# ── Agent Settlement ──────────────────────────────────────────────────────────

@router.post("/agent/payment", summary="Agent Payment Settlement")
async def agent_payment(req: AgentPaymentRequest):
    """
    Executes payment settlement for an AI agent using a valid Capability Token.
    Dispatches order to Razorpay and returns settlement proof.
    """
    payment_req = PaymentDispatchRequest(
        session_id=req.session_id,
        capability_token=req.capability_token,
        amount_paise=req.amount_paise,
    )

    resp = payment_service.dispatch_payment(payment_req)
    if not resp.success:
        return {
            "status": "REJECTED",
            "session_id": req.session_id,
            "error": resp.message,
        }

    return {
        "status": "SETTLED",
        "session_id": req.session_id,
        "razorpay_order_id": resp.razorpay_order_id,
        "amount_paise": resp.amount_paise,
        "currency": resp.currency,
        "payment_record_id": resp.payment_record_id,
    }
