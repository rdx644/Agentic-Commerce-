"""
Catalog data models — the source of truth for every price in the system.

Every downstream component (guardrail, checkout, upsell) resolves prices
against these models. The LLM never sets a price — it only references item_ids.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


class CatalogItem(BaseModel):
    """A single item in the merchant's catalog."""

    item_id: str = Field(..., description="Unique item identifier")
    name: str = Field(..., description="Human-readable product name")
    description: str = Field(default="", description="Product description")
    price_paise: int = Field(..., gt=0, description="Price in paise (₹1 = 100 paise)")
    currency: str = Field(default="INR", description="ISO 4217 currency code")
    category: str = Field(..., description="Product category for upsell matching")
    available: bool = Field(default=True, description="Whether item is in stock")
    tags: list[str] = Field(default_factory=list, description="Tags for cross-sell matching")
    image_url: str = Field(default="", description="Product image URL")

    @property
    def price_rupees(self) -> float:
        """Price in rupees for display purposes."""
        return self.price_paise / 100.0


class CatalogManifest(BaseModel):
    """
    Versioned, hashed catalog manifest — the single source of truth.

    Every quote in the system references a specific manifest version and hash.
    Price drift between quote-time and checkout-time is a diffable fact,
    not a guess.
    """

    version: str = Field(..., description="Semantic version of this catalog snapshot")
    hash: str = Field(..., description="SHA-256 hash of sorted items JSON")
    items: list[CatalogItem] = Field(..., description="All catalog items")
    merchant_id: str = Field(default="merchant_demo_001", description="Merchant identifier")
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO timestamp of manifest creation",
    )
    item_count: int = Field(default=0, description="Number of items in catalog")

    def model_post_init(self, __context) -> None:
        """Auto-compute item_count after initialization."""
        self.item_count = len(self.items)


class PriceDriftResult(BaseModel):
    """Result of checking whether a quoted price still matches the catalog."""

    match: bool = Field(..., description="True if price matches current catalog")
    item_id: str
    quoted_price_paise: int
    current_price_paise: int
    drift_paise: int = Field(default=0, description="Positive = item got more expensive")
    catalog_version: str
    catalog_hash: str


class CatalogLookupResult(BaseModel):
    """Result of looking up items from the catalog by their IDs."""

    found: list[CatalogItem] = Field(default_factory=list)
    missing_ids: list[str] = Field(default_factory=list)
    catalog_version: str
    catalog_hash: str
    total_paise: int = Field(default=0, description="Sum of found items' prices")
