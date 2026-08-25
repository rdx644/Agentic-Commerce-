"""
Payment API routes.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from src.payment.models import PaymentDispatchRequest, PaymentDispatchResponse, ReconciliationResult
from src.payment import service as payment_service
from src.payment import reconciliation
from src.security.auth import require_operator

router = APIRouter(prefix="/payment", tags=["payment"])


@router.post("/dispatch", response_model=PaymentDispatchResponse, summary="Dispatch Payment")
async def dispatch(request: PaymentDispatchRequest):
    """
    Dispatch payment to Razorpay. Requires a valid capability token
    from a guardrail PASS. Idempotent via receipt-based dedup.
    """
    return payment_service.dispatch_payment(request)


@router.post("/reconcile/{record_id}", response_model=ReconciliationResult, summary="Reconcile Payment", dependencies=[Depends(require_operator)])
async def reconcile_one(record_id: int):
    """Reconcile a single payment record against Razorpay's source of truth."""
    try:
        return reconciliation.reconcile_payment(record_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/reconcile-all", summary="Reconcile All Pending", dependencies=[Depends(require_operator)])
async def reconcile_all():
    """Reconcile all PENDING/CREATED payment records."""
    results = reconciliation.reconcile_all_pending()
    return {
        "total": len(results),
        "reconciled": sum(1 for r in results if r.reconciled),
        "dead_lettered": sum(1 for r in results if r.dead_lettered),
        "results": results,
    }
