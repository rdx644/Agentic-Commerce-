"""Upsell API routes."""

from fastapi import APIRouter

from src.upsell import service as upsell_service
from src.upsell.models import UpsellAcceptRequest, UpsellOfferRequest, UpsellResponse

router = APIRouter(prefix="/upsell", tags=["upsell"])


@router.post("/offer", response_model=UpsellResponse, summary="Generate Upsell Offer")
async def generate_offer(request: UpsellOfferRequest):
    """Generate one bounded offer for an authorised checkout session."""
    return upsell_service.generate_offer(request)


@router.post("/accept", response_model=UpsellResponse, summary="Accept Upsell Offer")
async def accept_offer(request: UpsellAcceptRequest):
    """Accept an offer through a fresh guardrail check."""
    return upsell_service.accept_upsell(request)
