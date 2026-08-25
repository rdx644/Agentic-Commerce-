"""
LLM integration — Gemini NL → structured intent parser.

CRITICAL INVARIANT: The LLM only ever produces intent (item_ids + ceiling).
Every price is resolved by deterministic code against the catalog.
The LLM never sets a price, never calls Razorpay, never makes a budget decision.
"""

from __future__ import annotations

import json
import logging
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


def parse_intent(message: str) -> ParsedIntent:
    """
    Parse natural language checkout message into structured intent using Gemini.

    The LLM output is ONLY intent — item references and a stated ceiling.
    All prices are resolved downstream by deterministic catalog lookups.
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

    client = _get_client()
    system_prompt = _build_system_prompt(catalog_items)

    models_to_try = ["gemini-3.6-flash", "gemini-3.7-flash", "gemini-2.5-flash"]
    last_error = None

    for model_name in models_to_try:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=message,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.1,  # Near-deterministic for structured parsing
                    max_output_tokens=500,
                    response_mime_type="application/json",
                ),
            )

            raw_text = response.text.strip()
            logger.debug("Gemini raw response: %s", raw_text)

            # Parse the JSON response
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
            last_error = e
            logger.warning("Gemini model %s failed: %s, trying next...", model_name, e)

    # Heuristic catalog fallback parser if all remote LLM calls fail
    logger.info("Executing heuristic intent fallback parser for message: %s", message)
    matched_items = []
    msg_lower = message.lower()
    for cat_item in catalog_items:
        name_lower = cat_item["name"].lower()
        if any(token in msg_lower for token in name_lower.split() if len(token) > 3):
            matched_items.append(ParsedCartItem(item_id=cat_item["item_id"], quantity=1))

    if matched_items:
        import re
        price_matches = re.findall(r"(?:under|budget|max|below|within|rs\.?|₹)\s*(\d+[\d,]*)", msg_lower)
        ceiling = 10000000  # Default ₹1,00,000 ceiling
        if price_matches:
            try:
                ceiling = int(price_matches[0].replace(",", "")) * 100
            except ValueError:
                pass
        return ParsedIntent(
            items=matched_items[:2],
            ceiling_paise=ceiling,
            confidence=0.85,
        )

    raise ValueError(f"LLM parsing failed: {last_error}")
