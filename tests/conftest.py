import os
import pytest

# Ensure testing settings are set before test suite execution
os.environ["APP_ENV"] = "test"
os.environ.setdefault("JWT_SECRET", "super-secret-key-for-testing-at-least-32-chars-long")
os.environ.setdefault("OPERATOR_USERNAME", "admin")
os.environ.setdefault("OPERATOR_PASSWORD", "test-operator-password-123")
