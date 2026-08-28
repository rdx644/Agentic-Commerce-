"""
FastAPI application entrypoint.

Mounts all routers, initializes database, serves dashboard.
"""

from __future__ import annotations

import logging
import os
import platform
from contextlib import asynccontextmanager
from datetime import datetime, timezone

# pyrefly: ignore [missing-import]
from fastapi import FastAPI
# pyrefly: ignore [missing-import]
from fastapi.staticfiles import StaticFiles
# pyrefly: ignore [missing-import]
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
# pyrefly: ignore [missing-import]
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from src.config import get_settings
from src.database import init_db
from src.observability import setup_observability
from src.security.middleware import SecurityHeadersMiddleware, RequestSizeLimitMiddleware

# Import routers
from src.catalog.router import router as catalog_router
from src.guardrail.router import router as guardrail_router
from src.checkout.router import router as checkout_router
from src.payment.router import router as payment_router
from src.webhook.router import router as webhook_router
from src.upsell.router import router as upsell_router
from src.campaign.router import router as campaign_router
from src.audit.router import router as audit_router
from src.security.auth import router as auth_router
from src.agent_protocol.router import router as agent_protocol_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database and seed catalog on startup."""
    settings = get_settings()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper()),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )

    # Initialize database
    init_db()
    logging.info("Database initialized at %s", settings.database_url)

    # Seed catalog if empty
    from src.catalog import service as catalog_service
    try:
        catalog_service.get_manifest()
        logging.info("Catalog already seeded")
    except ValueError:
        logging.info("Seeding catalog...")
        _seed_default_catalog()

    yield


def _seed_default_catalog():
    """Seed the default electronics store catalog."""
    from src.catalog.models import CatalogItem
    from src.catalog.service import seed_catalog

    items = [
        CatalogItem(
            item_id="phone_001",
            name="Quantum X Pro Smartphone",
            description="Flagship smartphone with AI camera, 256GB storage",
            price_paise=5999900,  # ₹59,999
            category="smartphones",
            tags=["electronics", "mobile", "flagship", "camera"],
        ),
        CatalogItem(
            item_id="phone_002",
            name="NeoLite 5G Phone",
            description="Mid-range 5G smartphone, 128GB storage",
            price_paise=1999900,  # ₹19,999
            category="smartphones",
            tags=["electronics", "mobile", "5g", "mid-range"],
        ),
        CatalogItem(
            item_id="earbuds_001",
            name="SoundPods Pro ANC",
            description="Active noise cancelling wireless earbuds",
            price_paise=499900,  # ₹4,999
            category="audio",
            tags=["electronics", "audio", "wireless", "anc"],
        ),
        CatalogItem(
            item_id="earbuds_002",
            name="BassBuds Lite",
            description="Wireless earbuds with 24hr battery",
            price_paise=149900,  # ₹1,499
            category="audio",
            tags=["electronics", "audio", "wireless", "budget"],
        ),
        CatalogItem(
            item_id="case_001",
            name="ArmorShield Phone Case",
            description="Military-grade protection case for Quantum X Pro",
            price_paise=99900,  # ₹999
            category="accessories",
            tags=["accessories", "protection", "mobile"],
        ),
        CatalogItem(
            item_id="charger_001",
            name="TurboCharge 65W GaN Charger",
            description="65W GaN fast charger with USB-C",
            price_paise=199900,  # ₹1,999
            category="accessories",
            tags=["accessories", "charging", "usb-c", "fast-charge"],
        ),
        CatalogItem(
            item_id="cable_001",
            name="FlexiCord USB-C Cable (2m)",
            description="Braided USB-C to USB-C cable, 100W PD",
            price_paise=49900,  # ₹499
            category="accessories",
            tags=["accessories", "cable", "usb-c"],
        ),
        CatalogItem(
            item_id="watch_001",
            name="PulseBand Smart Watch",
            description="Fitness tracker with heart rate, SpO2, GPS",
            price_paise=799900,  # ₹7,999
            category="wearables",
            tags=["electronics", "wearable", "fitness", "smartwatch"],
        ),
        CatalogItem(
            item_id="powerbank_001",
            name="JuiceBox 20000mAh Power Bank",
            description="20000mAh power bank with 45W PD output",
            price_paise=249900,  # ₹2,499
            category="accessories",
            tags=["accessories", "power", "portable", "usb-c"],
        ),
        CatalogItem(
            item_id="speaker_001",
            name="BoomBox Mini Bluetooth Speaker",
            description="Portable waterproof Bluetooth speaker, 12hr battery",
            price_paise=349900,  # ₹3,499
            category="audio",
            tags=["electronics", "audio", "bluetooth", "portable"],
        ),
    ]

    seed_catalog(items, version="1.0.0")
    logging.info("Seeded %d catalog items", len(items))


# ── Create FastAPI app ────────────────────────────────────────────────────────

settings = get_settings()

app = FastAPI(
    title="Agentic Commerce Platform",
    description=(
        "AI Growth & Agentic Commerce — Razorpay Buildathon Track 01. "
        "Every money action explainable, bounded, and gated."
    ),
    version="0.1.0",
    docs_url=None if settings.app_env == "production" else "/docs",
    redoc_url=None if settings.app_env == "production" else "/redoc",
    openapi_url=None if settings.app_env == "production" else "/openapi.json",
    lifespan=lifespan,
)

# Setup Observability
setup_observability(app)

# ── Security Middleware Stack (outermost runs first) ─────────────────────────

# 1. Security headers on ALL responses
app.add_middleware(SecurityHeadersMiddleware)

# 2. Reject oversized request bodies (1 MB limit)
app.add_middleware(RequestSizeLimitMiddleware, max_size=1 * 1024 * 1024)

# 3. Trusted host validation (prevent Host header attacks)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings.allowed_hosts_list,
)

# 4. CORS — locked to explicit origins instead of wildcard
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Razorpay-Signature", "X-Razorpay-Event-Id"],
)

# Mount routers
app.include_router(catalog_router)
app.include_router(guardrail_router)
app.include_router(checkout_router)
app.include_router(payment_router)
app.include_router(webhook_router)
app.include_router(upsell_router)
app.include_router(campaign_router)
app.include_router(audit_router)
app.include_router(auth_router)
app.include_router(agent_protocol_router)

# Serve dashboard static files
dashboard_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "dashboard")
if os.path.exists(dashboard_dir):
    app.mount("/dashboard/static", StaticFiles(directory=dashboard_dir), name="dashboard-static")


@app.get("/")
async def root():
    """Redirect root directly to the visual Architectural Blueprint dashboard."""
    return RedirectResponse(url="/dashboard")


@app.get("/api")
async def api_index():
    """API root — navigation."""
    return {
        "service": "Agentic Commerce Platform",
        "version": "0.1.0",
        "track": "01 — AI Growth & Agentic Commerce",
        "endpoints": {
            "health": "/health",
            "agent_discovery": "/.well-known/agent.json",
            "ucp_discovery": "/.well-known/ucp",
            "agent_catalog": "/agent/catalog",
            "agent_checkout": "/agent/checkout",
            "agent_authorize": "/agent/authorize",
            "agent_payment": "/agent/payment",
            "catalog": "/catalog",
            "checkout": "/checkout/converse",
            "guardrail": "/guardrail/check",
            "payment": "/payment/dispatch",
            "webhook": "/webhook/razorpay",
            "upsell": "/upsell/offer",
            "campaign": "/campaign/run",
            "audit_trail": "/audit/trail",
            "audit_stats": "/audit/stats",
            "audit_stream": "/audit/stream",
            "dashboard": "/dashboard",
            "docs": "/docs",
        },
    }


@app.get("/health", summary="Structured Health Check")
async def health_check():
    """
    Structured health endpoint for monitoring and readiness probes.
    Returns service status, version, uptime metadata, and dependency checks.
    """
    settings = get_settings()
    db_ok = False
    try:
        from src.database import get_db
        with get_db() as conn:
            conn.execute("SELECT 1").fetchone()
        db_ok = True
    except Exception:
        pass

    return {
        "status": "healthy" if db_ok else "degraded",
        "service": "agentic-commerce",
        "version": "0.1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": {
            "database": "ok" if db_ok else "fail",
            "razorpay_configured": bool(settings.razorpay_key_secret),
            "gemini_configured": bool(settings.gemini_api_key),
            "webhook_secret_set": bool(settings.razorpay_webhook_secret),
        },
        "environment": {
            "python": platform.python_version(),
            "platform": platform.system(),
            "log_level": settings.log_level,
        },
    }


@app.get("/dashboard")
async def dashboard():
    """Serve the audit dashboard."""
    dashboard_path = os.path.join(dashboard_dir, "index.html")
    if os.path.exists(dashboard_path):
        return FileResponse(dashboard_path)
    return {"error": "Dashboard not found", "path": dashboard_path}
