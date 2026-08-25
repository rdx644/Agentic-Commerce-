"""Operator authentication for administrative and audit surfaces.

Replaces HTTP Basic auth with OAuth2 (JWT) for enterprise-grade security.
Customer checkout remains capability-token based.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm

# pyrefly: ignore [missing-import]
from src.config import get_settings

router = APIRouter(prefix="/auth", tags=["Auth"])

_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)

def create_access_token(data: dict, expires_delta: timedelta) -> str:
    settings = get_settings()
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.jwt_secret, algorithm="HS256")
    return encoded_jwt


@router.post("/token")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    settings = get_settings()
    
    # In development with no password set, bypass check
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


def require_operator(
    token: str = Depends(_oauth2_scheme), 
    token_query: str = Query(None, alias="token")
) -> str:
    """Require a valid JWT token for operator endpoints. Supports query param for SSE."""
    settings = get_settings()
    
    # Allow frictionless bypass in local development if no password is set
    if settings.app_env != "production" and not settings.operator_password:
        return settings.operator_username
        
    actual_token = token or token_query
        
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    if not actual_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    try:
        payload = jwt.decode(actual_token, settings.jwt_secret, algorithms=["HS256"])
        username: str | None = payload.get("sub")
        if username is None:
            raise credentials_exception
    except jwt.InvalidTokenError:
        raise credentials_exception
        
    return username
