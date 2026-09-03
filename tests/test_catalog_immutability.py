"""
Catalog Version Immutability Test Suite.
Verifies that once a catalog version is sealed with a cryptographic hash,
any attempt to mutate that version is strictly rejected.
"""

import pytest
from src.database import init_db
from src.catalog.models import CatalogItem
from src.catalog.service import seed_catalog, get_manifest, _compute_hash


@pytest.fixture(autouse=True)
def setup_db():
    init_db()
    yield
    # Clean up test versions so they do not pollute the active catalog for subsequent tests
    from src.database import get_db_transaction
    from src.catalog.service import _invalidate_cache
    with get_db_transaction() as conn:
        conn.execute("DELETE FROM catalog_versions WHERE version LIKE 'immut-%'")
    _invalidate_cache()


def test_same_version_same_content_is_idempotent():
    """Re-seeding the same version with identical items is idempotent and succeeds."""
    items = [
        CatalogItem(item_id="item_a", name="Widget A", description="Desc", price_paise=1000, category="cat"),
        CatalogItem(item_id="item_b", name="Widget B", description="Desc", price_paise=2000, category="cat"),
    ]
    manifest1 = seed_catalog(items, version="immut-1.0.0")
    manifest2 = seed_catalog(items, version="immut-1.0.0")
    assert manifest1.hash == manifest2.hash
    assert manifest1.version == manifest2.version


def test_same_version_changed_content_is_rejected():
    """Attempting to change price, items, or contents of an existing version must raise ValueError."""
    items_v1 = [
        CatalogItem(item_id="item_a", name="Widget A", description="Desc", price_paise=1000, category="cat"),
    ]
    seed_catalog(items_v1, version="immut-2.0.0")

    # Tampered items with altered price
    items_tampered = [
        CatalogItem(item_id="item_a", name="Widget A", description="Desc", price_paise=999, category="cat"),
    ]

    with pytest.raises(ValueError, match="already exists with a different hash"):
        seed_catalog(items_tampered, version="immut-2.0.0")


def test_new_version_is_accepted():
    """A new semantic version is accepted without conflict."""
    items_v1 = [CatalogItem(item_id="item_v3_a", name="Widget V3", description="Desc", price_paise=1000, category="cat")]
    items_v2 = [CatalogItem(item_id="item_v3_a", name="Widget V3", description="Desc", price_paise=1200, category="cat")]

    m1 = seed_catalog(items_v1, version="immut-3.0.0")
    m2 = seed_catalog(items_v2, version="immut-3.1.0")
    assert m1.version != m2.version
    assert m1.hash != m2.hash


def test_hash_is_stable_regardless_of_item_ordering():
    """Hash computation must be deterministic and invariant to item order in the list."""
    item1 = CatalogItem(item_id="item_1", name="One", description="Desc", price_paise=100, category="cat")
    item2 = CatalogItem(item_id="item_2", name="Two", description="Desc", price_paise=200, category="cat")

    hash1 = _compute_hash([item1, item2])
    hash2 = _compute_hash([item2, item1])
    assert hash1 == hash2
