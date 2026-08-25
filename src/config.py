"""
Application configuration — all secrets and settings loaded from environment.
Razorpay keys, Gemini API key, JWT secret: NEVER hardcoded, NEVER committed.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    """Central settings — populated from .env or OS environment variables."""

    # ── Razorpay (test-mode) ──────────────────────────────────────────────
    razorpay_key_id: str = "rzp_test_xxxxxxxxxxxx"
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""

    # ── Gemini AI ─────────────────────────────────────────────────────────
    gemini_api_key: str = ""

    # ── Security ──────────────────────────────────────────────────────────
    app_env: Literal["development", "test", "production"] = "development"
    jwt_secret: str = "change-me-in-production"
    capability_token_ttl_seconds: int = 300  # 5 minutes
    operator_username: str = "operator"
    operator_password: str = ""

    # ── Database ──────────────────────────────────────────────────────────
    database_url: str = "postgresql://postgres:postgres@localhost:5432/agentic_commerce"

    # ── Server ────────────────────────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"

    # Comma-separated settings work well with standard container platforms.
    allowed_hosts: str = "localhost,127.0.0.1"
    cors_origins: str = "http://localhost:8000,http://127.0.0.1:8000"

    # ── Guardrail ─────────────────────────────────────────────────────────
    max_consecutive_rejections: int = 5
    max_reconciliation_attempts: int = 3
    retry_base_delay_seconds: float = 1.0
    retry_max_delay_seconds: float = 30.0

    # ── Campaign ──────────────────────────────────────────────────────────
    campaign_batch_size: int = 50  # total sessions (half baseline, half agent)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        """Fail closed when a deploy uses unsafe development defaults."""
        if self.app_env != "production":
            return self

        if self.jwt_secret == "change-me-in-production" or len(self.jwt_secret) < 32:
            raise ValueError("JWT_SECRET must be a unique value of at least 32 characters in production")
        if not self.razorpay_key_secret:
            raise ValueError("RAZORPAY_KEY_SECRET must be configured in production")
        if not self.razorpay_webhook_secret:
            raise ValueError("RAZORPAY_WEBHOOK_SECRET must be configured in production")
        if len(self.operator_password) < 16:
            raise ValueError("OPERATOR_PASSWORD must be at least 16 characters in production")
        if self.log_level.upper() == "DEBUG":
            raise ValueError("LOG_LEVEL must not be DEBUG in production")
        return self

    @property
    def allowed_hosts_list(self) -> list[str]:
        return [host.strip() for host in self.allowed_hosts.split(",") if host.strip()]

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache()
def get_settings() -> Settings:
    """Singleton settings instance — cached after first load."""
    return Settings()
