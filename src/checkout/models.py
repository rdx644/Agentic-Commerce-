"""
Checkout data models.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class CheckoutRequest(BaseModel):
    """Incoming checkout request from user/agent."""

    message: str = Field(
        ...,
        description="Natural language checkout message",
        min_length=1,
        max_length=2000,
    )
    session_id: str = Field(
        ...,
        description="Session identifier",
        min_length=1,
        max_length=64,
        pattern=r"^[a-zA-Z0-9_-]+$",
    )
    budget_paise: Optional[int] = Field(
        default=None,
        description="Optional explicit budget. If not set, extracted from message.",
        gt=0,
        le=10_000_000,  # Max ₹1 lakh
    )


class ParsedCartItem(BaseModel):
    """An item parsed from natural language by the LLM."""

    item_id: str = Field(..., min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$")
    quantity: int = Field(default=1, ge=1, le=100)


class ParsedIntent(BaseModel):
    """Structured intent produced by LLM parsing — ONLY intent, no prices."""

    items: list[ParsedCartItem]
    ceiling_paise: int = Field(..., gt=0, description="Stated spending ceiling")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    clarification_needed: Optional[str] = None


class CheckoutResponse(BaseModel):
    """Full checkout response with guardrail decision and payment info."""

    session_id: str
    message: str  # Human-readable response
    parsed_intent: Optional[ParsedIntent] = None
    guardrail_decision: Optional[str] = None  # PASS or REJECT
    guardrail_reason: Optional[str] = None
    resolved_total_paise: Optional[int] = None
    capability_token: Optional[str] = None
    razorpay_order_id: Optional[str] = None
    payment_status: Optional[str] = None
    upsell_offer: Optional[dict] = None
    catalog_version: Optional[str] = None
    catalog_hash: Optional[str] = None
