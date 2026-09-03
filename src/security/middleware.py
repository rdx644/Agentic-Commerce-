"""
Security middleware — HTTP security headers and request limits.

Applied to EVERY response. Based on OWASP Secure Headers recommendations.
"""

from __future__ import annotations

import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from src.config import get_settings

logger = logging.getLogger(__name__)

# Maximum request body size: 1 MB
MAX_BODY_SIZE = 1 * 1024 * 1024  # 1 MB


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Inject security headers into every HTTP response.

    Headers set:
    - X-Content-Type-Options: nosniff
    - X-Frame-Options: DENY
    - X-XSS-Protection: 0 (modern browsers disable, CSP replaces)
    - Referrer-Policy: strict-origin-when-cross-origin
    - Content-Security-Policy: restrictive default policy
    - Strict-Transport-Security: max-age=31536000
    - Permissions-Policy: restrict sensitive APIs
    - Cache-Control: no-store for API responses
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "0"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=(self)"
        )

        # Hardened CSP: No unsafe-inline in script-src, self-hosted Chart.js, object-src none
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com data:; "
            "img-src 'self' data: https:; "
            "connect-src 'self'; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "form-action 'self'; "
            "frame-ancestors 'none'"
        )

        # HSTS — only meaningful over HTTPS but safe to send always
        if get_settings().app_env == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        # Prevent aggressive browser caching of dashboard assets & ensure API privacy
        if request.url.path.startswith("/dashboard/static") or request.url.path == "/dashboard":
            response.headers["Cache-Control"] = "no-cache, must-revalidate"
        else:
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
            response.headers["Pragma"] = "no-cache"

        return response


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """
    Reject requests with bodies exceeding MAX_BODY_SIZE.
    Prevents denial-of-service via oversized payloads.
    """

    def __init__(self, app, max_size: int = MAX_BODY_SIZE):
        super().__init__(app)
        self.max_size = max_size

    async def dispatch(self, request: Request, call_next) -> Response:
        # Check Content-Length header first (cheap check)
        content_length = request.headers.get("content-length")
        try:
            declared_size = int(content_length) if content_length else None
        except ValueError:
            return Response(
                content='{"detail": "Invalid Content-Length"}',
                status_code=400,
                media_type="application/json",
            )

        if declared_size is not None and declared_size > self.max_size:
            logger.warning(
                "Request rejected: Content-Length %s exceeds limit %d",
                content_length, self.max_size,
            )
            return Response(
                content='{"detail": "Request body too large"}',
                status_code=413,
                media_type="application/json",
            )

        return await call_next(request)
