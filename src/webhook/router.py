"""
Webhook API routes.
"""

from __future__ import annotations

import asyncio
import logging
import re

from fastapi import APIRouter, Request, HTTPException

from src.webhook import handler as webhook_handler

logger = logging.getLogger(__name__)

# Maximum webhook payload size (1 MB)
_MAX_WEBHOOK_BODY = 1 * 1024 * 1024
# Allowed event types from Razorpay
_ALLOWED_EVENT_TYPES = {
    "payment.authorized", "payment.captured", "payment.failed",
    "order.paid", "refund.processed", "refund.failed",
}

router = APIRouter(prefix="/webhook", tags=["webhook"])


@router.post("/razorpay", summary="Razorpay Webhook Endpoint")
async def receive_webhook(request: Request):
    """
    Receive Razorpay webhooks with HMAC-SHA256 verification.
    Acks fast (200) and processes in background.
    """
    # Get raw body BEFORE any JSON parsing (critical for HMAC verification)
    raw_body = await request.body()

    # ── Payload size gate ─────────────────────────────────────────────────
    if len(raw_body) > _MAX_WEBHOOK_BODY:
        logger.warning("Webhook payload too large: %d bytes", len(raw_body))
        raise HTTPException(status_code=413, detail="Payload too large")

    # Extract signature from header
    signature = request.headers.get("x-razorpay-signature", "")
    if not signature:
        logger.warning("Webhook received without signature header")
        raise HTTPException(status_code=400, detail="Missing signature header")

    # ── HARD GATE: Verify HMAC signature ──────────────────────────────────
    if not webhook_handler.verify_signature(raw_body, signature):
        logger.warning("Webhook signature verification FAILED")
        raise HTTPException(status_code=400, detail="Invalid signature")

    # Parse payload after verification
    import json
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event_id = request.headers.get("x-razorpay-event-id", "")
    event_type = payload.get("event", "unknown")

    # ── Validate event_id format (prevent injection via header) ───────────
    if event_id and not re.match(r"^[a-zA-Z0-9_-]{1,128}$", event_id):
        logger.warning("Invalid event_id format: %s", event_id[:50])
        raise HTTPException(status_code=400, detail="Invalid event ID format")

    # ── Validate event type against allowlist ─────────────────────────────
    if event_type not in _ALLOWED_EVENT_TYPES:
        logger.info("Ignoring unhandled event type: %s", event_type)
        return {"status": "ignored", "event_type": event_type}

    # ── Dedup check ───────────────────────────────────────────────────────
    if webhook_handler.is_duplicate_event(event_id):
        logger.info("Duplicate webhook event: %s", event_id)
        return {"status": "duplicate", "event_id": event_id}

    # ── Ack fast, process async ───────────────────────────────────────────
    asyncio.create_task(_process_in_background(event_id, event_type, payload))

    return {"status": "accepted", "event_id": event_id}


async def _process_in_background(event_id: str, event_type: str, payload: dict):
    """Background processing of webhook event."""
    try:
        webhook_handler.process_webhook_event(event_id, event_type, payload)
    except Exception as e:
        logger.error("Background webhook processing failed: event=%s, error=%s", event_id, e)
