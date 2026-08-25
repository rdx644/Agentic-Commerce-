"""
Rate limiter — freeze sessions after N consecutive guardrail rejections.

Cheap to add, reads as mature threat modeling. Prevents abuse where
an agent or user hammers the guardrail trying to find a loophole.
"""

from __future__ import annotations

import logging

from src.config import get_settings
from src.guardrail.ledger import freeze_session, get_session_state

logger = logging.getLogger(__name__)


def check_and_freeze_if_needed(session_id: str) -> bool:
    """
    Check if session should be frozen based on consecutive rejections.
    Returns True if session is now frozen (or was already frozen).
    """
    settings = get_settings()
    state = get_session_state(session_id)

    if state is None:
        return False

    if state.frozen:
        return True

    if state.consecutive_rejections >= settings.max_consecutive_rejections:
        freeze_session(session_id)
        logger.warning(
            "Session auto-frozen after %d consecutive rejections: session=%s",
            state.consecutive_rejections,
            session_id,
        )
        return True

    return False
