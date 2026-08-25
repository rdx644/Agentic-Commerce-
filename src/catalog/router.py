"""
Catalog API routes.

Exposes:
- GET /.well-known/ucp — UCP-style discovery (mirrors Google's convention)
- GET /catalog — Full versioned manifest
- GET /catalog/{item_id} — Single item lookup
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from src.catalog import service as catalog_service
from src.catalog.models import CatalogItem, CatalogManifest

router = APIRouter(tags=["catalog"])


@router.get("/.well-known/ucp", summary="UCP Discovery Endpoint")
async def ucp_discovery():
    """
    Agent-readable discovery endpoint following the UCP convention.
    AI agents use this to discover the merchant's catalog capabilities.
    """
    try:
        manifest = catalog_service.get_manifest()
    except ValueError:
        raise HTTPException(status_code=503, detail="Catalog not yet initialized")

    return {
        "merchant_id": manifest.merchant_id,
        "name": "Agentic Commerce Demo Store",
        "capabilities": ["catalog_search", "checkout", "upsell"],
        "catalog_url": "/catalog",
        "checkout_url": "/checkout/converse",
        "catalog_version": manifest.version,
        "catalog_hash": manifest.hash,
        "item_count": manifest.item_count,
        "supported_currencies": ["INR"],
        "protocol_version": "1.0.0",
    }


@router.get("/catalog", response_model=CatalogManifest, summary="Full Catalog Manifest")
async def get_catalog():
    """
    Returns the full versioned, hashed catalog manifest.
    Every downstream component checks prices against this.
    """
    try:
        return catalog_service.get_manifest()
    except ValueError:
        raise HTTPException(status_code=503, detail="Catalog not yet initialized")


@router.get("/catalog/{item_id}", response_model=CatalogItem, summary="Single Item Lookup")
async def get_catalog_item(item_id: str):
    """Look up a single catalog item by ID."""
    item = catalog_service.get_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Item '{item_id}' not found")
    return item
