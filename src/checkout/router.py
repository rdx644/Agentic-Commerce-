"""
Checkout API routes.
"""

from __future__ import annotations

from fastapi import APIRouter

from src.checkout.models import CheckoutRequest, CheckoutResponse
from src.checkout import service as checkout_service

router = APIRouter(prefix="/checkout", tags=["checkout"])


@router.post("/converse", response_model=CheckoutResponse, summary="Conversational Checkout")
async def converse(request: CheckoutRequest):
    """
    Submit a natural language checkout message.
    The system parses intent, validates against catalog, runs guardrail checks,
    and returns approval with capability token or rejection with reason.
    """
    return checkout_service.process_checkout(request)
