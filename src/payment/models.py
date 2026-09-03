"""
Payment data models.
"""

from __future__ import annotations

from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field

# Shared upper bound for all financial payment interfaces (₹10,00,000 = 100,000,000 paise)
MAX_PAYMENT_PAISE: int = 100_000_000


class PaymentDispatchRequest(BaseModel):
    """Request to dispatch payment to Razorpay."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    capability_token: str = Field(..., min_length=1, max_length=4096, description="JWT from guardrail PASS")
    amount_paise: int = Field(..., gt=0, le=MAX_PAYMENT_PAISE)
    currency: str = Field(default="INR", pattern=r"^INR$")
    item_ids: Optional[List[str]] = Field(None, max_length=50, description="Optional items to verify against capability scope")


class PaymentDispatchResponse(BaseModel):
    """Response from payment dispatch."""

    session_id: str
    success: bool
    razorpay_order_id: Optional[str] = None
    idempotency_key: str = ""
    amount_paise: int = 0
    currency: str = "INR"
    status: str = ""
    message: str = ""
    payment_record_id: Optional[int] = None


class ReconciliationResult(BaseModel):
    """Result of reconciling a payment with Razorpay."""

    payment_record_id: int
    session_id: str
    razorpay_order_id: str
    local_status: str
    razorpay_status: str
    reconciled: bool
    action_taken: str
    dead_lettered: bool = False
