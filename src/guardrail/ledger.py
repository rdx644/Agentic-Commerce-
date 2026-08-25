"""
Budget ledger — atomic conditional writes for spend tracking.

THE critical invariant: budget check is ONE atomic conditional DB write,
never a separate read-then-write. This prevents race conditions where
concurrent requests could both read "enough budget" and both succeed.

SQL pattern:
    UPDATE budget_ledger
    SET spent_paise = spent_paise + %s
    WHERE session_id = %s AND spent_paise + %s <= budget_paise
    -- If rowcount == 0, the budget was exceeded. No separate read needed.
"""

from __future__ import annotations

import logging
from typing import Optional

from src.database import get_db, get_db_transaction
from src.guardrail.models import SessionBudgetState

logger = logging.getLogger(__name__)


def init_session_budget(session_id: str, budget_paise: int, agent_id: str = "default") -> SessionBudgetState:
    """
    Create a new session budget entry.
    Called once at session start — sets the hard ceiling for this session.
    """
    with get_db_transaction() as conn:
        conn.execute(
            """
            INSERT INTO budget_ledger
            (session_id, agent_id, budget_paise, spent_paise, consecutive_rejections, frozen)
            VALUES (%s, %s, %s, 0, 0, 0)
            ON CONFLICT (session_id) DO NOTHING
            """,
            (session_id, agent_id, budget_paise),
        )

    logger.info("Budget initialized: session=%s, budget=%d paise", session_id, budget_paise)
    return get_session_state(session_id)


def atomic_spend(session_id: str, amount_paise: int) -> bool:
    """
    THE atomic budget check — one conditional write, never read-then-write.

    Returns True if spend was accepted, False if budget exceeded.
    On success, spent_paise is atomically incremented and consecutive_rejections reset.
    On failure, consecutive_rejections is atomically incremented.
    """
    with get_db_transaction() as conn:
        # Atomic conditional update — this IS the budget check
        cursor = conn.execute(
            """
            UPDATE budget_ledger
            SET spent_paise = spent_paise + %s,
                consecutive_rejections = 0,
                updated_at = CURRENT_TIMESTAMP
            WHERE session_id = %s
              AND frozen = 0
              AND spent_paise + %s <= budget_paise
            """,
            (amount_paise, session_id, amount_paise),
        )

        if cursor.rowcount == 1:
            logger.info(
                "Budget check PASSED: session=%s, amount=%d paise",
                session_id,
                amount_paise,
            )
            return True

        # Budget exceeded or session frozen — increment rejection counter
        conn.execute(
            """
            UPDATE budget_ledger
            SET consecutive_rejections = consecutive_rejections + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE session_id = %s AND frozen = 0
            """,
            (session_id,),
        )

        logger.warning(
            "Budget check REJECTED: session=%s, amount=%d paise",
            session_id,
            amount_paise,
        )
        return False


def freeze_session(session_id: str) -> None:
    """Freeze a session after too many consecutive rejections."""
    with get_db_transaction() as conn:
        conn.execute(
            """
            UPDATE budget_ledger
            SET frozen = 1, updated_at = CURRENT_TIMESTAMP
            WHERE session_id = %s
            """,
            (session_id,),
        )
    logger.warning("Session FROZEN: session=%s", session_id)


def get_session_state(session_id: str) -> Optional[SessionBudgetState]:
    """Get current budget state for a session."""
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT session_id, budget_paise, spent_paise, consecutive_rejections, frozen
            FROM budget_ledger
            WHERE session_id = %s
            """,
            (session_id,),
        ).fetchone()

    if row is None:
        return None

    return SessionBudgetState(
        session_id=row["session_id"],
        budget_paise=row["budget_paise"],
        spent_paise=row["spent_paise"],
        remaining_paise=row["budget_paise"] - row["spent_paise"],
        consecutive_rejections=row["consecutive_rejections"],
        frozen=bool(row["frozen"]),
    )
