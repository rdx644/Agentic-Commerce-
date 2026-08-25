import os
import socket
import pytest

# Ensure testing settings are set before test suite execution
os.environ["APP_ENV"] = "test"

# Auto-detect local postgres port (5433 for local docker compose, 5432 for CI runner)
if "DATABASE_URL" not in os.environ:
    def is_port_open(port: int) -> bool:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except (socket.timeout, ConnectionRefusedError, OSError):
            return False

    if is_port_open(5433):
        os.environ["DATABASE_URL"] = "postgresql://postgres:postgres@127.0.0.1:5433/agentic_commerce"
    else:
        os.environ["DATABASE_URL"] = "postgresql://user:password@127.0.0.1:5432/agentic_commerce_test"

os.environ.setdefault("JWT_SECRET", "super-secret-key-for-testing-at-least-32-chars-long")
os.environ.setdefault("OPERATOR_USERNAME", "admin")
os.environ.setdefault("OPERATOR_PASSWORD", "test-operator-password-123")
os.environ.setdefault("RAZORPAY_KEY_ID", "rzp_test_dummy123456789")
os.environ.setdefault("RAZORPAY_KEY_SECRET", "dummy_razorpay_secret_123456")
os.environ.setdefault("RAZORPAY_WEBHOOK_SECRET", "dummy_webhook_secret_123456")
os.environ.setdefault("GEMINI_API_KEY", "dummy_gemini_api_key_123456")
os.environ.setdefault("LOG_LEVEL", "INFO")
os.environ.setdefault("ALLOWED_HOSTS", "*")
