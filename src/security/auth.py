"""Operator authentication for administrative and audit surfaces.

Replaces HTTP Basic auth with OAuth2 (JWT) for enterprise-grade security.
Customer checkout remains capability-token based.
SSE streaming uses short-lived, single-use stream tickets (never raw JWT in URLs).
"""

from __future__ import annotations

import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm

from src.config import get_settings

router = APIRouter(prefix="/auth", tags=["Auth"])

_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)

# In-memory single-use stream ticket cache: ticket_id -> expiry_epoch
_stream_tickets: dict[str, float] = {}


def create_access_token(data: dict, expires_delta: timedelta) -> str:
    settings = get_settings()
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.jwt_secret, algorithm="HS256")
    return encoded_jwt


@router.post("/token", summary="Operator Login")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    settings = get_settings()

    if settings.app_env != "production" and not settings.operator_password:
        valid = True
    else:
        valid = (
            secrets.compare_digest(form_data.username, settings.operator_username)
            and secrets.compare_digest(form_data.password, settings.operator_password)
        )

    if not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(hours=12)
    access_token = create_access_token(
        data={"sub": form_data.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


def require_operator(token: str = Depends(_oauth2_scheme)) -> str:
    """Require a valid Bearer JWT token in the Authorization header."""
    settings = get_settings()

    if settings.app_env != "production" and not settings.operator_password:
        return settings.operator_username

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Provide Authorization: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        username: str | None = payload.get("sub")
        if username is None:
            raise credentials_exception
    except jwt.InvalidTokenError:
        raise credentials_exception

    return username


@router.post("/stream-ticket", summary="Mint Single-Use SSE Stream Ticket")
async def create_stream_ticket(current_user: str = Depends(require_operator)):
    """
    Mints a single-use, 30-second cryptographic stream ticket for SSE connections.
    Avoids exposing long-lived Bearer JWTs in URL query strings.
    """
    now = time.time()
    # Clean expired tickets
    expired = [t for t, exp in _stream_tickets.items() if exp < now]
    for t in expired:
        _stream_tickets.pop(t, None)

    ticket = f"st_{secrets.token_urlsafe(24)}"
    _stream_tickets[ticket] = now + 30.0  # 30-second TTL
    return {"ticket": ticket, "expires_in_seconds": 30}


def validate_and_consume_stream_ticket(ticket: Optional[str]) -> bool:
    """
    Validates and immediately burns a single-use stream ticket.
    Returns True if valid and not expired, False otherwise.
    """
    if not ticket:
        return False

    now = time.time()
    expiry = _stream_tickets.pop(ticket, None)
    if expiry is not None and expiry >= now:
        return True
    return False


def require_operator_or_ticket(
    token: str = Depends(_oauth2_scheme),
    ticket: Optional[str] = Query(None, alias="ticket"),
) -> str:
    """Authentication gate for SSE stream: accepts valid Bearer token OR single-use ticket."""
    settings = get_settings()

    if settings.app_env != "production" and not settings.operator_password:
        return settings.operator_username

    # 1. Check single-use ticket
    if ticket and validate_and_consume_stream_ticket(ticket):
        return "stream_subscriber"

    # 2. Check Bearer JWT token
    if token:
        try:
            payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
            username = payload.get("sub")
            if username:
                return username
        except jwt.InvalidTokenError:
            pass

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unauthorized. Provide a valid stream ticket via ?ticket= or Authorization header.",
        headers={"WWW-Authenticate": "Bearer"},
    )
