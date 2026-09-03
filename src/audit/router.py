"""
Audit API routes — includes SSE stream for real-time dashboard updates.
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from src.audit import service as audit_service
from src.database import get_db
from src.security.auth import require_operator, require_operator_optional, require_operator_or_ticket

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/trail", summary="Audit Trail", dependencies=[Depends(require_operator_optional)])
async def get_trail(
    session_id: str = Query(None),
    action: str = Query(None),
    failure_class: str = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0, ge=0),
):
    """Query the audit trail with optional filters."""
    return audit_service.get_audit_trail(
        session_id=session_id,
        action=action,
        failure_class=failure_class,
        limit=limit,
        offset=offset,
    )


@router.get("/stats", summary="Audit Statistics", dependencies=[Depends(require_operator_optional)])
async def get_stats():
    """Aggregate statistics from the audit trail."""
    return audit_service.get_audit_stats()


@router.get("/session/{session_id}", summary="Session Detail", dependencies=[Depends(require_operator)])
async def get_session(session_id: str):
    """
    Full detail for a specific session — audit trail + budget + payments.
    Operator authorization strictly required (Section 3 & 23).
    """
    return audit_service.get_session_detail(session_id)


@router.get("/export", summary="Audit Export", dependencies=[Depends(require_operator)])
async def export_audit(limit: int = Query(500, le=5000)):
    """Export complete audit ledger for compliance review. Operator only."""
    return audit_service.get_audit_trail(limit=limit)


@router.get("/stream", summary="Real-time SSE Stream")
async def stream_audit(auth_user: str = Depends(require_operator_or_ticket)):
    """
    Server-Sent Events stream of audit log entries.
    Emits sanitized DTOs for public observers and complete payloads for operators.
    """
    is_operator = (auth_user == "operator")

    async def event_generator():
        last_id = 0
        with get_db() as conn:
            row = conn.execute("SELECT MAX(id) as max_id FROM audit_log").fetchone()
            if row and row["max_id"]:
                last_id = row["max_id"]

        while True:
            with get_db() as conn:
                rows = conn.execute(
                    "SELECT * FROM audit_log WHERE id > %s ORDER BY id ASC LIMIT 20",
                    (last_id,),
                ).fetchall()

            for row in rows:
                entry = dict(row)
                last_id = entry["id"]
                payload = entry if is_operator else audit_service.sanitize_audit_entry(entry)
                yield f"data: {json.dumps(payload, default=str)}\n\n"

            # Also send stats periodically
            if not rows:
                stats = audit_service.get_audit_stats()
                yield f"event: stats\ndata: {json.dumps(stats, default=str)}\n\n"

            await asyncio.sleep(2)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
