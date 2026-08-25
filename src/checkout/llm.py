"""
LLM integration — Gemini NL → structured intent parser.

CRITICAL INVARIANT: The LLM only ever produces intent (item_ids + ceiling).
Every price is resolved by deterministic code against the catalog.
The LLM never sets a price, never calls Razorpay, never makes a budget decision.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

from google import genai
from google.genai import types

from src.config import get_settings
from src.catalog import service as catalog_service
from src.checkout.models import ParsedCartItem, ParsedIntent

logger = logging.getLogger(__name__)

# ── Gemini client (lazy init) ────────────────────────────────────────────────

_client: Optional[genai.Client] = None


def _get_client() -> genai.Client:
    """Lazy-init Gemini client."""
    global _client
    if _client is None:
        settings = get_settings()
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


def _build_system_prompt(catalog_items: list[dict]) -> str:
    """Build the system prompt with current catalog context."""
    items_text = json.dumps(catalog_items, indent=2)
    return f"""You are a checkout assistant for an electronics store. Your ONLY job is to parse a customer's natural language message into a structured shopping intent.

AVAILABLE CATALOG ITEMS:
{items_text}

RULES:
1. Extract which items the customer wants to buy (map to item_id from catalog).
2. Extract quantities (default to 1 if not specified).
3. Extract their spending ceiling/budget in paise (₹1 = 100 paise). If they say "₹5000" that's 500000 paise.
4. If the customer's message is unclear, set clarification_needed to a short question.
5. You MUST only reference item_ids that exist in the catalog above.
6. You NEVER set or negotiate prices. Prices come from the catalog.
7. If budget is not mentioned, estimate a reasonable ceiling at 120% of the total catalog price for requested items.

Respond with ONLY valid JSON in this exact format:
{{
  "items": [{{"item_id": "string", "quantity": number}}],
  "ceiling_paise": number,
  "confidence": number between 0 and 1,
  "clarification_needed": "string or null"
}}"""


def _heuristic_parse(message: str, catalog_items: list[dict]) -> ParsedIntent:
    """High-precision deterministic fallback parser when remote LLM is unavailable."""
    msg_lower = message.lower()
    
    # 1. Extract explicit budget ceiling if mentioned
    budget_paise = None
    budget_patterns = [
        r"(?:budget|under|below|max|ceiling|within|limit)\s*(?:of|is|:)?\s*(?:rs\.?|₹|inr)?\s*(\d+[\d,]*)",
        r"(?:rs\.?|₹|inr)\s*(\d+[\d,]*)",
        r"(\d+[\d,]*)\s*(?:rupees|rs|inr)",
    ]
    for pattern in budget_patterns:
        match = re.search(pattern, msg_lower)
        if match:
            try:
                num_str = match.group(1).replace(",", "")
                budget_paise = int(num_str) * 100
                break
            except ValueError:
                pass

    # 2. Match catalog items by scoring token overlaps and exact phrases
    scored_items: list[tuple[int, dict, int]] = []  # (score, catalog_item, quantity)
    
    for item in catalog_items:
        item_name = item["name"].lower()
        item_id = item["item_id"].lower()
        score = 0
        
        # Exact name match
        if item_name in msg_lower or item_id in msg_lower:
            score += 100
        else:
            # Token match
            tokens = [t for t in item_name.split() if len(t) > 2]
            for t in tokens:
                if t in msg_lower:
                    score += 20
        
        if score > 0:
            # Extract quantity near the item name if possible
            qty = 1
            qty_match = re.search(rf"(\d+)\s*(?:x\s*)?(?:of\s+)?{re.escape(item_name)}", msg_lower)
            if not qty_match:
                qty_match = re.search(rf"{re.escape(item_name)}\s*(?:x\s*)?(\d+)", msg_lower)
            if not qty_match:
                # Generic leading quantity like "buy 2 ..."
                leading_qty = re.search(r"(?:buy|order|purchase|get|want)\s+(\d+)\b", msg_lower)
                if leading_qty:
                    qty_match = leading_qty

            if qty_match:
                try:
                    qty = max(1, min(100, int(qty_match.group(1))))
                except ValueError:
                    qty = 1

            scored_items.append((score, item, qty))

    # Sort items by highest match score
    scored_items.sort(key=lambda x: x[0], reverse=True)

    if not scored_items:
        return ParsedIntent(
            items=[],
            ceiling_paise=budget_paise or 10000000,
            confidence=0.0,
            clarification_needed="I could not identify any products from our catalog in your message. Available items include Quantum X Pro, Ultra Wireless Pods, Pro Gaming Mouse, and Mechanical Keyboard.",
        )

    # Pick the best matched item(s) (highest scoring items)
    top_score = scored_items[0][0]
    selected_items = [
        ParsedCartItem(item_id=it[1]["item_id"], quantity=it[2])
        for it in scored_items
        if it[0] >= top_score - 10
    ][:3]

    # Calculate default ceiling if none provided (120% of catalog price)
    if budget_paise is None:
        total_est = sum(
            next((it["price_rupees"] * 100 for it in catalog_items if it["item_id"] == p.item_id), 0) * p.quantity
            for p in selected_items
        )
        budget_paise = int(total_est * 1.2) if total_est > 0 else 10000000

    return ParsedIntent(
        items=selected_items,
        ceiling_paise=budget_paise,
        confidence=0.9,
    )


def parse_intent(message: str) -> ParsedIntent:
    """
    Parse natural language checkout message into structured intent using Gemini
    with robust heuristic fallback.
    """
    # Get current catalog for context
    try:
        manifest = catalog_service.get_manifest()
        catalog_items = [
            {
                "item_id": item.item_id,
                "name": item.name,
                "price_rupees": item.price_paise / 100,
                "category": item.category,
                "available": item.available,
            }
            for item in manifest.items
            if item.available
        ]
    except ValueError:
        raise ValueError("Catalog not initialized. Cannot parse checkout intent.")

    try:
        client = _get_client()
        system_prompt = _build_system_prompt(catalog_items)

        # Standard supported Gemini models
        models_to_try = ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"]

        for model_name in models_to_try:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=message,
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        temperature=0.1,
                        max_output_tokens=500,
                        response_mime_type="application/json",
                    ),
                )

                raw_text = response.text.strip()
                logger.debug("Gemini raw response: %s", raw_text)

                parsed = json.loads(raw_text)

                items = [
                    ParsedCartItem(item_id=item["item_id"], quantity=item.get("quantity", 1))
                    for item in parsed.get("items", [])
                ]

                return ParsedIntent(
                    items=items,
                    ceiling_paise=int(parsed.get("ceiling_paise", 0)),
                    confidence=float(parsed.get("confidence", 1.0)),
                    clarification_needed=parsed.get("clarification_needed"),
                )
            except Exception as e:
                logger.warning("Gemini model %s failed: %s, trying next...", model_name, e)
    except Exception as e:
        logger.warning("Gemini client initialization failed: %s. Falling back to heuristic parser.", e)

    # Deterministic high-precision fallback parser
    logger.info("Executing heuristic intent fallback parser for message: %s", message)
    return _heuristic_parse(message, catalog_items)
