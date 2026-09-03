"""
Catalog service — versioned, hashed, cached manifest management.

Design invariants:
- Every price check goes through this service, never direct DB reads.
- Catalog is cached with a 60s TTL, refreshed lazily.
- Hash is computed deterministically: SHA-256 of sorted items JSON.
- Every quote references a catalog version+hash so price drift is diffable.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Optional

from src.catalog.models import (
    CatalogItem,
    CatalogLookupResult,
    CatalogManifest,
    PriceDriftResult,
)
from src.database import get_db, get_db_transaction

logger = logging.getLogger(__name__)

# ── In-memory cache ──────────────────────────────────────────────────────────

_cached_manifest: Optional[CatalogManifest] = None
_cache_timestamp: float = 0.0
_CACHE_TTL_SECONDS: float = 60.0


def _compute_hash(items: list[CatalogItem]) -> str:
    """Deterministic SHA-256 hash of sorted catalog items."""
    items_data = [item.model_dump() for item in sorted(items, key=lambda x: x.item_id)]
    raw = json.dumps(items_data, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _invalidate_cache() -> None:
    """Force cache refresh on next read."""
    global _cache_timestamp
    _cache_timestamp = 0.0


def seed_catalog(items: list[CatalogItem], version: str = "1.0.0") -> CatalogManifest:
    """
    Seed the catalog with a new version.
    Each version is an IMMUTABLE snapshot — same version + different content is rejected.
    Same version + same content is idempotent (safe).
    """
    catalog_hash = _compute_hash(items)

    manifest = CatalogManifest(
        version=version,
        hash=catalog_hash,
        items=items,
    )

    items_json = json.dumps(
        [item.model_dump() for item in items],
        sort_keys=True,
        default=str,
    )

    with get_db_transaction() as conn:
        # Immutable insert — DO NOTHING on conflict (never overwrite)
        conn.execute(
            """
            INSERT INTO catalog_versions (version, hash, items_json)
            VALUES (%s, %s, %s)
            ON CONFLICT (version) DO NOTHING
            """,
            (version, catalog_hash, items_json),
        )

    # Verify: if version already existed, hashes must match
    with get_db() as conn:
        existing = conn.execute(
            "SELECT hash FROM catalog_versions WHERE version = %s",
            (version,),
        ).fetchone()

    if existing and existing["hash"] != catalog_hash:
        raise ValueError(
            f"Catalog version '{version}' already exists with a different hash. "
            f"Existing: {existing['hash'][:16]}..., Requested: {catalog_hash[:16]}... "
            f"Catalog versions are immutable — create a new version instead."
        )

    _invalidate_cache()
    logger.info("Catalog seeded: version=%s, hash=%s, items=%d", version, catalog_hash[:12], len(items))
    return manifest


def get_manifest() -> CatalogManifest:
    """
    Get current catalog manifest with caching.
    Cache TTL is 60s — refreshed lazily on next request after expiry.
    """
    global _cached_manifest, _cache_timestamp

    now = time.time()
    if _cached_manifest is not None and (now - _cache_timestamp) < _CACHE_TTL_SECONDS:
        return _cached_manifest

    with get_db() as conn:
        row = conn.execute(
            "SELECT version, hash, items_json FROM catalog_versions ORDER BY created_at DESC LIMIT 1"
        ).fetchone()

    if row is None:
        raise ValueError("No catalog found. Run seed_catalog() first.")

    items_data = json.loads(row["items_json"])
    items = [CatalogItem(**item) for item in items_data]

    manifest = CatalogManifest(
        version=row["version"],
        hash=row["hash"],
        items=items,
    )

    _cached_manifest = manifest
    _cache_timestamp = now
    logger.debug("Catalog cache refreshed: version=%s", manifest.version)
    return manifest


def get_item(item_id: str) -> Optional[CatalogItem]:
    """Look up a single item by ID from the current catalog."""
    manifest = get_manifest()
    for item in manifest.items:
        if item.item_id == item_id:
            return item
    return None


def lookup_items(item_ids: list[str], quantities: Optional[list[int]] = None) -> CatalogLookupResult:
    """
    Look up multiple items by ID, compute total, report missing.
    Used by checkout to resolve LLM intent against real catalog prices.
    """
    manifest = get_manifest()
    item_map = {item.item_id: item for item in manifest.items}

    found: list[CatalogItem] = []
    missing: list[str] = []
    total_paise = 0

    qtys = quantities or [1] * len(item_ids)

    for item_id, qty in zip(item_ids, qtys):
        if item_id in item_map and item_map[item_id].available:
            item = item_map[item_id]
            found.append(item)
            total_paise += item.price_paise * qty
        else:
            missing.append(item_id)

    return CatalogLookupResult(
        found=found,
        missing_ids=missing,
        catalog_version=manifest.version,
        catalog_hash=manifest.hash,
        total_paise=total_paise,
    )


def check_price_drift(
    item_id: str,
    quoted_price_paise: int,
    quoted_catalog_hash: str,
) -> PriceDriftResult:
    """
    Check if a quoted price still matches the current catalog.
    This is the guardrail's price-drift check — a diffable fact, not a guess.
    """
    manifest = get_manifest()
    item = None
    for catalog_item in manifest.items:
        if catalog_item.item_id == item_id:
            item = catalog_item
            break

    if item is None:
        return PriceDriftResult(
            match=False,
            item_id=item_id,
            quoted_price_paise=quoted_price_paise,
            current_price_paise=0,
            drift_paise=-quoted_price_paise,
            catalog_version=manifest.version,
            catalog_hash=manifest.hash,
        )

    drift = item.price_paise - quoted_price_paise
    return PriceDriftResult(
        match=(drift == 0 and manifest.hash == quoted_catalog_hash),
        item_id=item_id,
        quoted_price_paise=quoted_price_paise,
        current_price_paise=item.price_paise,
        drift_paise=drift,
        catalog_version=manifest.version,
        catalog_hash=manifest.hash,
    )


def get_upsell_candidates(
    cart_item_ids: list[str],
    max_price_paise: int,
) -> list[CatalogItem]:
    """
    Find catalog items suitable for upsell — same category/tags, not already in cart,
    within budget. Used by the upsell agent to pick bounded add-ons.
    """
    manifest = get_manifest()
    cart_set = set(cart_item_ids)

    # Collect categories and tags from cart items
    cart_categories: set[str] = set()
    cart_tags: set[str] = set()
    for item in manifest.items:
        if item.item_id in cart_set:
            cart_categories.add(item.category)
            cart_tags.update(item.tags)

    candidates = []
    for item in manifest.items:
        if item.item_id in cart_set:
            continue
        if not item.available:
            continue
        if item.price_paise > max_price_paise:
            continue
        # Match by category or overlapping tags
        if item.category in cart_categories or bool(set(item.tags) & cart_tags):
            candidates.append(item)

    # Sort by price ascending (cheapest upsell first — bounded)
    candidates.sort(key=lambda x: x.price_paise)
    return candidates
