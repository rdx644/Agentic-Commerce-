"""
Audit service — query the audit log, aggregate stats, SSE stream.

This reads from the SAME ledger the guardrail writes to.
The audit trail is a real table, not app logs.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from src.database import get_db

logger = logging.getLogger(__name__)


def sanitize_audit_entry(entry: dict) -> dict:
    """Sanitize internal or sensitive fields from audit logs for public observers."""
    sanitized = {
        "id": entry.get("id"),
        "created_at": str(entry.get("created_at")),
        "session_id": entry.get("session_id"),
        "action": entry.get("action"),
        "decision": entry.get("decision"),
        "amount_paise": entry.get("amount_paise"),
        "failure_class": entry.get("failure_class"),
        "reason": entry.get("reason"),
        "actor": entry.get("actor"),
    }
    if "metadata_json" in entry and entry["metadata_json"]:
        try:
            meta = json.loads(entry["metadata_json"]) if isinstance(entry["metadata_json"], str) else entry["metadata_json"]
            safe_meta = {}
            for k, v in meta.items():
                if any(sec in k.lower() for sec in ("token", "jwt", "secret", "password", "key")):
                    safe_meta[k] = "[REDACTED]"
                elif isinstance(v, str) and len(v) > 200:
                    safe_meta[k] = v[:200] + "..."
                else:
                    safe_meta[k] = v
            sanitized["metadata"] = safe_meta
        except Exception:
            sanitized["metadata"] = {}
    return sanitized


def get_audit_trail(
    session_id: Optional[str] = None,
    action: Optional[str] = None,
    failure_class: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """
    Query the audit trail with optional filters.
    Returns chronological list of audit entries.
    """
    conditions = []
    params = []

    if session_id:
        conditions.append("session_id = %s")
        params.append(session_id)
    if action:
        conditions.append("action = %s")
        params.append(action)
    if failure_class:
        conditions.append("failure_class = %s")
        params.append(failure_class)

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    with get_db() as conn:
        rows = conn.execute(
            f"""
            SELECT * FROM audit_log
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
            """,
            params + [limit, offset],
        ).fetchall()

    return [dict(row) for row in rows]


def get_audit_stats() -> dict:
    """Aggregate statistics from the audit trail."""
    with get_db() as conn:
        # Total entries
        total = conn.execute("SELECT COUNT(*) as c FROM audit_log").fetchone()["c"]

        # By action
        actions = conn.execute(
            "SELECT action, COUNT(*) as c FROM audit_log GROUP BY action ORDER BY c DESC"
        ).fetchall()

        # By decision
        decisions = conn.execute(
            "SELECT decision, COUNT(*) as c FROM audit_log WHERE decision IS NOT NULL GROUP BY decision"
        ).fetchall()

        # By failure class
        failures = conn.execute(
            """SELECT failure_class, COUNT(*) as c FROM audit_log
            WHERE failure_class IS NOT NULL GROUP BY failure_class ORDER BY c DESC"""
        ).fetchall()

        # Recent activity (last 10)
        recent = conn.execute(
            "SELECT * FROM audit_log ORDER BY created_at DESC LIMIT 10"
        ).fetchall()

        # Payment stats
        payment_stats = conn.execute(
            """SELECT status, COUNT(*) as c, SUM(amount_paise) as total
            FROM payment_records GROUP BY status"""
        ).fetchall()

        # Budget ledger summary
        budget_stats = conn.execute(
            """SELECT COUNT(*) as sessions,
                   SUM(budget_paise) as total_budget,
                   SUM(spent_paise) as total_spent,
                   SUM(CASE WHEN frozen = 1 THEN 1 ELSE 0 END) as frozen_sessions
            FROM budget_ledger"""
        ).fetchone()

        # Dead letter count
        dead_letters = conn.execute(
            "SELECT COUNT(*) as c FROM dead_letter_queue WHERE resolved = 0"
        ).fetchone()["c"]

    return {
        "total_entries": total,
        "by_action": {row["action"]: row["c"] for row in actions},
        "by_decision": {row["decision"]: row["c"] for row in decisions},
        "by_failure_class": {row["failure_class"]: row["c"] for row in failures},
        "recent": [dict(row) for row in recent],
        "payment_stats": [
            {"status": row["status"], "count": row["c"], "total_paise": row["total"]}
            for row in payment_stats
        ],
        "budget_summary": {
            "total_sessions": budget_stats["sessions"] or 0,
            "total_budget_paise": budget_stats["total_budget"] or 0,
            "total_spent_paise": budget_stats["total_spent"] or 0,
            "frozen_sessions": budget_stats["frozen_sessions"] or 0,
        },
        "unresolved_dead_letters": dead_letters,
    }


def get_session_detail(session_id: str) -> dict:
    """Get full detail for a specific session — audit trail + budget + payments."""
    with get_db() as conn:
        audit = conn.execute(
            "SELECT * FROM audit_log WHERE session_id = %s ORDER BY created_at ASC",
            (session_id,),
        ).fetchall()

        budget = conn.execute(
            "SELECT * FROM budget_ledger WHERE session_id = %s",
            (session_id,),
        ).fetchone()

        payments = conn.execute(
            "SELECT * FROM payment_records WHERE session_id = %s ORDER BY created_at ASC",
            (session_id,),
        ).fetchall()

    return {
        "session_id": session_id,
        "audit_trail": [dict(row) for row in audit],
        "budget": dict(budget) if budget else None,
        "payments": [dict(row) for row in payments],
    }
