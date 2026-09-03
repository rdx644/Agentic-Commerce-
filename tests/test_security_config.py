"""
Security Configuration & Secret Hygiene Tests.
Verifies fail-closed behavior for production settings and ensures no privileged
credentials or secrets are leaked in code, HTML, or JavaScript.
"""

import os
from pathlib import Path
import pytest
from pydantic import ValidationError
from src.config import Settings


def test_production_fails_without_operator_username():
    with pytest.raises(ValueError, match="OPERATOR_USERNAME must be configured"):
        Settings(
            app_env="production",
            operator_username="",
            operator_password="A" * 20,
            jwt_secret="B" * 36,
            razorpay_key_secret="sec_123",
            razorpay_webhook_secret="whsec_123",
            payment_simulation_enabled=False,
            database_url="postgresql://user:pass@localhost:5432/db",
        )


def test_production_fails_without_operator_password():
    with pytest.raises(ValueError, match="OPERATOR_PASSWORD must be configured"):
        Settings(
            app_env="production",
            operator_username="admin",
            operator_password="",
            jwt_secret="B" * 36,
            razorpay_key_secret="sec_123",
            razorpay_webhook_secret="whsec_123",
            payment_simulation_enabled=False,
            database_url="postgresql://user:pass@localhost:5432/db",
        )


def test_production_fails_with_weak_operator_password():
    with pytest.raises(ValueError, match="at least 16 characters"):
        Settings(
            app_env="production",
            operator_username="admin",
            operator_password="short",
            jwt_secret="B" * 36,
            razorpay_key_secret="sec_123",
            razorpay_webhook_secret="whsec_123",
            payment_simulation_enabled=False,
            database_url="postgresql://user:pass@localhost:5432/db",
        )


def test_production_fails_with_default_jwt_secret():
    with pytest.raises(ValueError, match="JWT_SECRET must be a unique value"):
        Settings(
            app_env="production",
            operator_username="admin",
            operator_password="A" * 20,
            jwt_secret="change-me-in-production",
            razorpay_key_secret="sec_123",
            razorpay_webhook_secret="whsec_123",
            payment_simulation_enabled=False,
            database_url="postgresql://user:pass@localhost:5432/db",
        )


def test_production_fails_if_simulation_enabled():
    with pytest.raises(ValueError, match="PAYMENT_SIMULATION_ENABLED must be false"):
        Settings(
            app_env="production",
            operator_username="admin",
            operator_password="A" * 20,
            jwt_secret="B" * 36,
            razorpay_key_secret="sec_123",
            razorpay_webhook_secret="whsec_123",
            payment_simulation_enabled=True,
            database_url="postgresql://user:pass@localhost:5432/db",
        )


def test_production_fails_with_sqlite():
    with pytest.raises(ValueError, match="DATABASE_URL must be PostgreSQL"):
        Settings(
            app_env="production",
            operator_username="admin",
            operator_password="A" * 20,
            jwt_secret="B" * 36,
            razorpay_key_secret="sec_123",
            razorpay_webhook_secret="whsec_123",
            payment_simulation_enabled=False,
            database_url="sqlite:///test.db",
        )


def test_production_fails_with_debug_log_level():
    with pytest.raises(ValueError, match="LOG_LEVEL must not be DEBUG"):
        Settings(
            app_env="production",
            operator_username="admin",
            operator_password="A" * 20,
            jwt_secret="B" * 36,
            razorpay_key_secret="sec_123",
            razorpay_webhook_secret="whsec_123",
            payment_simulation_enabled=False,
            database_url="postgresql://user:pass@localhost:5432/db",
            log_level="DEBUG",
        )


def test_no_hardcoded_password_in_dashboard_source():
    """Verify that neither HTML nor JavaScript contains hardcoded demo password literals."""
    dashboard_dir = Path("dashboard")
    html_files = list(dashboard_dir.glob("*.html"))
    js_files = list(dashboard_dir.glob("*.js"))
    
    forbidden = ["RazorPay@123456#", "password123", "admin123"]
    
    for f in html_files + js_files:
        content = f.read_text(encoding="utf-8")
        for bad in forbidden:
            assert bad not in content, f"Found forbidden secret '{bad}' in {f}"
