"""
PostgreSQL database — schema initialization and connection management.

Design decisions:
- PostgreSQL chosen for robust concurrency, reliability, and enterprise scale.
- ConnectionPool is used for efficient connection multiplexing.
- Budget ledger uses atomic conditional UPDATE (one write, never read-then-write).
- All tables are real queryable tables, not app logs — this IS the audit trail.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Generator

import psycopg
from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row

from src.config import get_settings

logger = logging.getLogger(__name__)

# Global connection pool
_pool: ConnectionPool | None = None

# ── Schema ────────────────────────────────────────────────────────────────────

SCHEMA_SQL = """
-- Catalog versions (immutable snapshots)
CREATE TABLE IF NOT EXISTS catalog_versions (
    version      TEXT PRIMARY KEY,
    hash         TEXT NOT NULL UNIQUE,
    items_json   TEXT NOT NULL,
    created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Budget ledger (partitioned by session_id — no global lock)
CREATE TABLE IF NOT EXISTS budget_ledger (
    session_id              TEXT PRIMARY KEY,
    agent_id                TEXT,
    budget_paise            INTEGER NOT NULL,
    spent_paise             INTEGER NOT NULL DEFAULT 0,
    consecutive_rejections  INTEGER NOT NULL DEFAULT 0,
    frozen                  INTEGER NOT NULL DEFAULT 0,
    created_at              TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at              TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Audit log (queryable chronological ledger — THE audit trail)
CREATE TABLE IF NOT EXISTS audit_log (
    id                  SERIAL PRIMARY KEY,
    session_id          TEXT NOT NULL,
    action              TEXT NOT NULL,
    decision            TEXT,
    failure_class       TEXT,
    reason              TEXT,
    amount_paise        INTEGER,
    catalog_version     TEXT,
    catalog_hash        TEXT,
    actor               TEXT,
    capability_token_id TEXT,
    razorpay_order_id   TEXT,
    razorpay_payment_id TEXT,
    metadata_json       TEXT,
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Payment records (our ledger — written BEFORE calling Razorpay)
CREATE TABLE IF NOT EXISTS payment_records (
    id                  SERIAL PRIMARY KEY,
    session_id          TEXT NOT NULL,
    idempotency_key     TEXT NOT NULL UNIQUE,
    razorpay_order_id   TEXT,
    razorpay_payment_id TEXT,
    amount_paise        INTEGER NOT NULL,
    currency            TEXT NOT NULL DEFAULT 'INR',
    status              TEXT NOT NULL DEFAULT 'PENDING',
    attempts            INTEGER NOT NULL DEFAULT 0,
    last_error          TEXT,
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Webhook event deduplication
CREATE TABLE IF NOT EXISTS webhook_events (
    event_id     TEXT PRIMARY KEY,
    event_type   TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    processed    INTEGER NOT NULL DEFAULT 0,
    created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Dead letter queue (failed reconciliation after N attempts)
CREATE TABLE IF NOT EXISTS dead_letter_queue (
    id                SERIAL PRIMARY KEY,
    session_id        TEXT NOT NULL,
    payment_record_id INTEGER,
    failure_class     TEXT NOT NULL,
    reason            TEXT NOT NULL,
    attempts          INTEGER NOT NULL,
    payload_json      TEXT,
    created_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved          INTEGER NOT NULL DEFAULT 0,
    resolved_at       TIMESTAMP
);

-- Campaign session results
CREATE TABLE IF NOT EXISTS campaign_sessions (
    id                  SERIAL PRIMARY KEY,
    campaign_id         TEXT NOT NULL,
    session_id          TEXT NOT NULL,
    group_type          TEXT NOT NULL,
    converted           INTEGER NOT NULL DEFAULT 0,
    basket_size_paise   INTEGER NOT NULL DEFAULT 0,
    upsell_offered      INTEGER NOT NULL DEFAULT 0,
    upsell_accepted     INTEGER NOT NULL DEFAULT 0,
    upsell_amount_paise INTEGER NOT NULL DEFAULT 0,
    duration_ms         INTEGER,
    failure_class       TEXT,
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_audit_session ON audit_log(session_id);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action);
CREATE INDEX IF NOT EXISTS idx_audit_failure ON audit_log(failure_class);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at);
CREATE INDEX IF NOT EXISTS idx_payment_session ON payment_records(session_id);
CREATE INDEX IF NOT EXISTS idx_payment_status ON payment_records(status);
CREATE INDEX IF NOT EXISTS idx_campaign_id ON campaign_sessions(campaign_id);
"""


def init_db() -> None:
    """Initialize the connection pool and create all tables if they don't exist."""
    global _pool
    settings = get_settings()
    
    # Initialize the connection pool
    if not _pool:
        _pool = ConnectionPool(
            settings.database_url,
            min_size=1,
            max_size=20,
            kwargs={"row_factory": dict_row}
        )
    
    # Run migrations / create tables
    with _pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
        conn.commit()
    logger.info("PostgreSQL Database initialized")


def close_db() -> None:
    """Close the global connection pool."""
    global _pool
    if _pool:
        _pool.close()
        _pool = None
        logger.info("PostgreSQL Database connection pool closed")


@contextmanager
def get_db() -> Generator[psycopg.Connection, None, None]:
    """
    Context manager for database connections (default isolation level).
    Uses dict_row for dict-like access.
    """
    global _pool
    if not _pool:
        raise RuntimeError("Database pool is not initialized. Call init_db() first.")
    
    with _pool.connection() as conn:
        yield conn


@contextmanager
def get_db_transaction() -> Generator[psycopg.Connection, None, None]:
    """
    Context manager for explicit write transactions.
    In psycopg v3, connections are in a transaction by default (unless autocommit=True).
    This manager yields the connection and commits on exit, or rolls back on exception.
    """
    global _pool
    if not _pool:
        raise RuntimeError("Database pool is not initialized. Call init_db() first.")
    
    with _pool.connection() as conn:
        try:
            with conn.transaction():
                yield conn
        except Exception:
            # The context manager automatically rolls back the transaction
            raise
