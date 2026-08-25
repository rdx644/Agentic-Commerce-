"""
Guardrail data models — the types that flow through the spend-gate.

Key design: SpendIntent is what the LLM produces (via structured parsing).
GuardrailDecision is what the guardrail outputs. The LLM never touches
GuardrailDecision or anything downstream of it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class FailureClass(str, Enum):
    """Structured failure taxonomy — queryable by class in the audit trail."""

    GUARDRAIL_REJECT = "guardrail-reject"
    PRICE_DRIFT = "price-drift"
    BUDGET_EXCEEDED = "budget-exceeded"
    SESSION_FROZEN = "session-frozen"
    TOKEN_EXPIRED = "token-expired"
    TOKEN_INVALID = "token-invalid"
    ITEM_UNAVAILABLE = "item-unavailable"
    NETWORK_FAIL = "network-fail"
    WEBHOOK_MISMATCH = "webhook-mismatch"
    RECONCILIATION_FAIL = "reconciliation-fail"


class Decision(str, Enum):
    """Binary guardrail decision."""

    PASS = "PASS"
    REJECT = "REJECT"


class CartItem(BaseModel):
    """A single item in a spend intent — references catalog by item_id."""

    item_id: str
    quantity: int = Field(default=1, ge=1)
    # Price is NEVER set by the LLM — resolved from catalog
    resolved_price_paise: Optional[int] = None


class SpendIntent(BaseModel):
    """
    What the agent/user wants to spend — produced by NL parsing.
    This is the ONLY input to the guardrail. Never a raw amount.
    """

    session_id: str
    items: list[CartItem]
    stated_ceiling_paise: int = Field(..., gt=0, description="User's stated max spend")
    catalog_hash: str = Field(..., description="Hash of catalog used when building this intent")
    actor: str = Field(default="user", description="Who initiated: user | agent | system")
    intent_type: str = Field(default="checkout", description="checkout | upsell")


class GuardrailCheck(BaseModel):
    """Individual check result within the guardrail."""

    check_name: str
    passed: bool
    detail: str


class GuardrailDecision(BaseModel):
    """
    The guardrail's output — logged BEFORE any Razorpay call.
    Contains the full chain of reasoning for auditability.
    """

    decision: Decision
    session_id: str
    checks_performed: list[GuardrailCheck]
    reason: str
    failure_class: Optional[FailureClass] = None
    resolved_total_paise: int = Field(default=0, description="Total from catalog prices, not LLM")
    catalog_version: str = ""
    catalog_hash: str = ""
    capability_token: Optional[str] = None  # JWT string, only on PASS
    capability_token_id: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class SessionBudgetState(BaseModel):
    """Current state of a session's budget in the ledger."""

    session_id: str
    budget_paise: int
    spent_paise: int
    remaining_paise: int
    consecutive_rejections: int
    frozen: bool
