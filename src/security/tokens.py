"""
Capability tokens — short-TTL signed JWTs that authorize payment dispatch.

Design:
- Issued by the guardrail on PASS decision only.
- Contains: token_id, session_id, max_spend_paise, merchant_id, allowed_item_ids, expiry.
- Required by payment dispatch — no token, no Razorpay call.
- 5-minute TTL — forces re-validation if checkout is slow.
- Signed with server-side secret, never Razorpay keys.
- Includes `iss` (issuer) and `aud` (audience) claims for defense-in-depth.
- PERSISTENT: token record is written to capability_tokens table on issuance.
- SINGLE-USE: consumed atomically before Razorpay settlement.
"""

from __future__ import annotations

import json
import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt

from src.config import get_settings
from src.database import get_db_transaction

logger = logging.getLogger(__name__)

# Token claims constants
_TOKEN_ISSUER = "agentic-commerce-guardrail"
_TOKEN_AUDIENCE = "agentic-commerce-payment"


class TokenPayload:
    """Decoded capability token contents."""

    def __init__(
        self,
        token_id: str,
        session_id: str,
        max_spend_paise: int,
        merchant_id: str,
        allowed_item_ids: list[str],
        issued_at: datetime,
        expires_at: datetime,
    ):
        self.token_id = token_id
        self.session_id = session_id
        self.max_spend_paise = max_spend_paise
        self.merchant_id = merchant_id
        self.allowed_item_ids = allowed_item_ids
        self.issued_at = issued_at
        self.expires_at = expires_at


def issue_capability_token(
    session_id: str,
    max_spend_paise: int,
    allowed_item_ids: list[str],
    merchant_id: str = "merchant_demo_001",
) -> tuple[str, str]:
    """
    Issue a short-TTL capability token after guardrail PASS.
    Persists the token record in the capability_tokens table.

    Returns (token_string, token_id).
    """
    settings = get_settings()
    token_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    expiry = now + timedelta(seconds=settings.capability_token_ttl_seconds)

    payload = {
        "token_id": token_id,
        "session_id": session_id,
        "max_spend_paise": max_spend_paise,
        "merchant_id": merchant_id,
        "allowed_item_ids": allowed_item_ids,
        "iss": _TOKEN_ISSUER,
        "aud": _TOKEN_AUDIENCE,
        "iat": int(now.timestamp()),
        "exp": int(expiry.timestamp()),
    }

    token = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")

    # ── Persist token record for single-use enforcement ───────────────────
    with get_db_transaction() as conn:
        conn.execute(
            """
            INSERT INTO capability_tokens
            (token_id, session_id, merchant_id, authorized_amount_paise,
             allowed_item_ids, issued_at, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                token_id,
                session_id,
                merchant_id,
                max_spend_paise,
                json.dumps(allowed_item_ids),
                now.isoformat(),
                expiry.isoformat(),
            ),
        )

    logger.info(
        "Capability token issued: id=%s, session=%s, max_spend=%d, ttl=%ds",
        token_id[:8],
        session_id,
        max_spend_paise,
        settings.capability_token_ttl_seconds,
    )
    return token, token_id


def verify_capability_token(token: str) -> Optional[TokenPayload]:
    """
    Verify and decode a capability token.
    Returns None if expired, tampered, or invalid.
    Does NOT consume — consumption happens atomically at payment dispatch.
    """
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            issuer=_TOKEN_ISSUER,
            audience=_TOKEN_AUDIENCE,
        )
        return TokenPayload(
            token_id=payload["token_id"],
            session_id=payload["session_id"],
            max_spend_paise=payload["max_spend_paise"],
            merchant_id=payload["merchant_id"],
            allowed_item_ids=payload["allowed_item_ids"],
            issued_at=datetime.fromtimestamp(payload["iat"], tz=timezone.utc),
            expires_at=datetime.fromtimestamp(payload["exp"], tz=timezone.utc),
        )
    except jwt.ExpiredSignatureError:
        logger.warning("Capability token expired")
        return None
    except jwt.InvalidAudienceError:
        logger.warning("Capability token has invalid audience claim")
        return None
    except jwt.InvalidIssuerError:
        logger.warning("Capability token has invalid issuer claim")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning("Capability token invalid: %s", e)
        return None
    except (KeyError, ValueError) as e:
        logger.warning("Capability token missing required claims: %s", e)
        return None


def consume_capability_token(token_id: str) -> bool:
    """
    Atomically consume a capability token (single-use enforcement).
    Returns True if consumed successfully (first use).
    Returns False if already consumed, expired, or nonexistent.
    """
    with get_db_transaction() as conn:
        cursor = conn.execute(
            """
            UPDATE capability_tokens
            SET consumed_at = CURRENT_TIMESTAMP
            WHERE token_id = %s
              AND consumed_at IS NULL
              AND expires_at > CURRENT_TIMESTAMP
            """,
            (token_id,),
        )
        consumed = cursor.rowcount == 1

    if consumed:
        logger.info("Capability token consumed: %s", token_id[:8])
    else:
        logger.warning("Capability token consumption failed (expired/consumed/missing): %s", token_id[:8])

    return consumed
