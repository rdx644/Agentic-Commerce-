"""
Upsell agent data models.
"""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class UpsellOfferRequest(BaseModel):
    """Request to generate an upsell offer for a session."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    cart_item_ids: list[str] = Field(..., min_length=1, max_length=20, description="Items already in cart")
    remaining_budget_paise: int = Field(..., gt=0, le=10_000_000)
    capability_token: str = Field(..., min_length=1, max_length=4096, description="Original checkout token")


class UpsellAcceptRequest(BaseModel):
    """Acceptance requires the checkout authority for the same session."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    offer: "UpsellOffer"
    capability_token: str = Field(..., min_length=1, max_length=4096)


class UpsellOffer(BaseModel):
    """A bounded upsell offer from the catalog."""

    item_id: str
    name: str
    price_paise: int
    reason: str = Field(..., description="Why this item complements the cart")
    catalog_version: str
    catalog_hash: str


class UpsellResponse(BaseModel):
    """Response with upsell offer and decision."""

    session_id: str
    offer: Optional[UpsellOffer] = None
    accepted: bool = False
    guardrail_decision: Optional[str] = None
    guardrail_reason: Optional[str] = None
    message: str = ""
