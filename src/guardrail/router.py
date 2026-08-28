"""
Guardrail API routes.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from src.guardrail.models import SpendIntent, GuardrailDecision, SessionBudgetState
from src.guardrail import service as guardrail_service
from src.security.auth import require_operator, require_operator_optional

router = APIRouter(prefix="/guardrail", tags=["guardrail"])


@router.post("/check", response_model=GuardrailDecision, summary="Run Guardrail Check")
async def check_spend(intent: SpendIntent):
    """
    Submit a spend intent to the guardrail.
    Returns PASS with capability token, or REJECT with reason.
    """
    return guardrail_service.check_spend(intent)


@router.get("/session/{session_id}", response_model=SessionBudgetState, summary="Session Budget State")
async def get_session_state(session_id: str, _: str = Depends(require_operator_optional)):
    """Get current budget state for a session."""
    state = budget_ledger.get_session_state(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return state


@router.post("/session/{session_id}/init", response_model=SessionBudgetState, summary="Initialize Session Budget")
async def init_session(session_id: str, budget_paise: int = 1000000, _: None = Depends(require_operator)):
    """Initialize a session with a budget (default ₹10,000 = 1,000,000 paise)."""
    return budget_ledger.init_session_budget(session_id, budget_paise)
