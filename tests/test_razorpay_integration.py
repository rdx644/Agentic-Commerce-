"""
Live Razorpay Test-Mode Integration Tests.

Runs against live Razorpay Test API when valid test credentials are provided.
Skipped automatically in offline/mock CI environments.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import uuid
import pytest
import razorpay

from src.config import get_settings


def _has_real_credentials() -> bool:
    settings = get_settings()
    key_id = settings.razorpay_key_id
    secret = settings.razorpay_key_secret
    return bool(key_id and secret and not key_id.startswith("rzp_test_dummy") and key_id.startswith("rzp_test_"))


@pytest.mark.skipif(not _has_real_credentials(), reason="Real Razorpay test credentials not configured in environment")
def test_live_razorpay_order_creation_and_signature_verification():
    """
    Test real Razorpay test-mode order creation and cryptographic signature verification.
    """
    settings = get_settings()
    client = razorpay.Client(auth=(settings.razorpay_key_id, settings.razorpay_key_secret))

    session_id = f"live-test-{uuid.uuid4().hex[:8]}"
    amount_paise = 49900  # ₹499
    currency = "INR"
    receipt = f"rcpt_{session_id}"

    # 1. Create real test-mode order
    order_data = {
        "amount": amount_paise,
        "currency": currency,
        "receipt": receipt,
        "notes": {
            "session_id": session_id,
            "system": "Agentic Commerce Platform",
            "track": "01",
        },
    }
    order = client.order.create(data=order_data)

    assert order is not None
    assert "id" in order
    assert order["id"].startswith("order_")
    assert order["amount"] == amount_paise
    assert order["currency"] == currency
    assert order["status"] == "created"

    # 2. Cryptographic signature check simulation
    fake_payment_id = f"pay_{uuid.uuid4().hex[:14]}"
    raw_signature_body = f"{order['id']}|{fake_payment_id}".encode("utf-8")
    generated_signature = hmac.new(
        settings.razorpay_key_secret.encode("utf-8"),
        raw_signature_body,
        hashlib.sha256,
    ).hexdigest()

    # Verify signature
    client.utility.verify_payment_signature({
        "razorpay_order_id": order["id"],
        "razorpay_payment_id": fake_payment_id,
        "razorpay_signature": generated_signature,
    })
