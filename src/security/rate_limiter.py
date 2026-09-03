from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Optional

from fastapi import Request, HTTPException, status

from src.config import get_settings
from src.guardrail.ledger import freeze_session, get_session_state

logger = logging.getLogger(__name__)


class HTTPRateLimiter:
    """
    In-memory sliding-window HTTP rate limiter for sensitive transactional API routes.
    Tracks request timestamps per (client_ip, endpoint) bucket.
    """

    def __init__(self, requests_per_minute: int = 60):
        self.requests_per_minute = requests_per_minute
        self._history: dict[str, list[float]] = defaultdict(list)

    def check(self, key: str, max_requests: Optional[int] = None) -> bool:
        settings = get_settings()
        # In automated test suite, do not throttle unless explicitly configured
        if settings.app_env.lower() in ("test", "testing"):
            return True

        now = time.time()
        window = 60.0
        limit = max_requests or self.requests_per_minute

        timestamps = self._history[key]
        valid_timestamps = [t for t in timestamps if now - t < window]
        self._history[key] = valid_timestamps

        if len(valid_timestamps) >= limit:
            return False

        self._history[key].append(now)
        return True


# Global shared rate limiter instance
_global_limiter = HTTPRateLimiter(requests_per_minute=60)


async def rate_limit_endpoint(request: Request, limit: int = 60) -> None:
    """
    FastAPI dependency to rate limit sensitive transactional routes.
    Throws HTTP 429 when rate ceiling is breached.
    """
    client_ip = request.client.host if request.client else "unknown"
    key = f"{client_ip}:{request.url.path}"
    if not _global_limiter.check(key, max_requests=limit):
        logger.warning("Rate limit exceeded for %s on %s", client_ip, request.url.path)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Rate limit exceeded, please retry shortly.",
        )


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
