"""
Seed script — populate catalog with demo electronics store data.
Run: python -m scripts.seed_catalog
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import init_db
from src.catalog.models import CatalogItem
from src.catalog.service import seed_catalog


def main():
    init_db()

    items = [
        CatalogItem(
            item_id="phone_001",
            name="Quantum X Pro Smartphone",
            description="Flagship smartphone with AI camera, 256GB storage",
            price_paise=5999900,
            category="smartphones",
            tags=["electronics", "mobile", "flagship", "camera"],
        ),
        CatalogItem(
            item_id="phone_002",
            name="NeoLite 5G Phone",
            description="Mid-range 5G smartphone, 128GB storage",
            price_paise=1999900,
            category="smartphones",
            tags=["electronics", "mobile", "5g", "mid-range"],
        ),
        CatalogItem(
            item_id="earbuds_001",
            name="SoundPods Pro ANC",
            description="Active noise cancelling wireless earbuds",
            price_paise=499900,
            category="audio",
            tags=["electronics", "audio", "wireless", "anc"],
        ),
        CatalogItem(
            item_id="earbuds_002",
            name="BassBuds Lite",
            description="Wireless earbuds with 24hr battery",
            price_paise=149900,
            category="audio",
            tags=["electronics", "audio", "wireless", "budget"],
        ),
        CatalogItem(
            item_id="case_001",
            name="ArmorShield Phone Case",
            description="Military-grade protection case",
            price_paise=99900,
            category="accessories",
            tags=["accessories", "protection", "mobile"],
        ),
        CatalogItem(
            item_id="charger_001",
            name="TurboCharge 65W GaN Charger",
            description="65W GaN fast charger with USB-C",
            price_paise=199900,
            category="accessories",
            tags=["accessories", "charging", "usb-c", "fast-charge"],
        ),
        CatalogItem(
            item_id="cable_001",
            name="FlexiCord USB-C Cable (2m)",
            description="Braided USB-C to USB-C cable, 100W PD",
            price_paise=49900,
            category="accessories",
            tags=["accessories", "cable", "usb-c"],
        ),
        CatalogItem(
            item_id="watch_001",
            name="PulseBand Smart Watch",
            description="Fitness tracker with heart rate, SpO2, GPS",
            price_paise=799900,
            category="wearables",
            tags=["electronics", "wearable", "fitness", "smartwatch"],
        ),
        CatalogItem(
            item_id="powerbank_001",
            name="JuiceBox 20000mAh Power Bank",
            description="20000mAh power bank with 45W PD output",
            price_paise=249900,
            category="accessories",
            tags=["accessories", "power", "portable", "usb-c"],
        ),
        CatalogItem(
            item_id="speaker_001",
            name="BoomBox Mini Bluetooth Speaker",
            description="Portable waterproof Bluetooth speaker",
            price_paise=349900,
            category="audio",
            tags=["electronics", "audio", "bluetooth", "portable"],
        ),
    ]

    manifest = seed_catalog(items, version="1.0.0")
    print(f"✅ Catalog seeded: {manifest.item_count} items, version={manifest.version}, hash={manifest.hash[:16]}...")


if __name__ == "__main__":
    main()
