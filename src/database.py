"""
PostgreSQL & SQLite Database layer — schema initialization and connection management.

Design decisions:
- PostgreSQL chosen for robust production concurrency, reliability, and enterprise scale.
- SQLite supported for zero-dependency local testing and development with thread-safe WAL locking.
- ConnectionPool is used for PostgreSQL multiplexing.
- Budget ledger uses atomic conditional UPDATE (one write, never read-then-write).
- All tables are real queryable tables, not app logs — this IS the audit trail.
"""

from __future__ import annotations

import logging
import os
import re
import sqlite3
import threading
from contextlib import contextmanager
from typing import Any, Generator, Optional

from src.config import get_settings

logger = logging.getLogger(__name__)

# Global connection pool / state
_pool: Any = None
_is_sqlite: bool = False
_sqlite_path: str = "file:agentic_test_shared?mode=memory&cache=shared"
_sqlite_write_lock = threading.RLock()
_local = threading.local()


# ── Unified Schema ────────────────────────────────────────────────────────────

POSTGRES_SCHEMA_SQL = """
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

SQLITE_SCHEMA_SQL = POSTGRES_SCHEMA_SQL.replace("SERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT")


# ── SQLite Thread-Safe Adapter ────────────────────────────────────────────────

class SQLiteCursorWrapper:
    def __init__(self, cursor: sqlite3.Cursor):
        self._cursor = cursor

    def execute(self, sql: str, params: Optional[tuple | list | dict] = None) -> SQLiteCursorWrapper:
        adapted_sql = sql.replace("%s", "?")
        adapted_sql = re.sub(r"\bNOW\(\)", "CURRENT_TIMESTAMP", adapted_sql, flags=re.IGNORECASE)
        if params is not None:
            p = tuple(params) if isinstance(params, list) else params
            self._cursor.execute(adapted_sql, p)
        else:
            self._cursor.execute(adapted_sql)
        return self

    def fetchone(self) -> Optional[dict]:
        row = self._cursor.fetchone()
        return dict(row) if row is not None else None

    def fetchall(self) -> list[dict]:
        rows = self._cursor.fetchall()
        return [dict(r) for r in rows]

    @property
    def rowcount(self) -> int:
        return self._cursor.rowcount


class SQLiteConnWrapper:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def execute(self, sql: str, params: Optional[tuple | list | dict] = None) -> SQLiteCursorWrapper:
        cur = self._conn.cursor()
        wrapper = SQLiteCursorWrapper(cur)
        return wrapper.execute(sql, params)

    def cursor(self) -> SQLiteCursorWrapper:
        return SQLiteCursorWrapper(self._conn.cursor())

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass

    @contextmanager
    def transaction(self):
        with _sqlite_write_lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                yield self
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise


def _get_sqlite_connection() -> SQLiteConnWrapper:
    global _sqlite_path
    if not hasattr(_local, "conn") or _local.conn is None:
        # Check if URI mode needed
        uri_mode = _sqlite_path.startswith("file:")
        conn = sqlite3.connect(_sqlite_path, uri=uri_mode, check_same_thread=False, timeout=30.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=10000;")
        _local.conn = conn
    return SQLiteConnWrapper(_local.conn)


# ── Initialization ────────────────────────────────────────────────────────────

def init_db(max_retries: int = 3, retry_delay: float = 0.5) -> None:
    """Initialize database schema with automatic PostgreSQL/SQLite detection."""
    global _pool, _is_sqlite, _sqlite_path
    settings = get_settings()
    db_url = settings.database_url

    if db_url.startswith("sqlite"):
        _is_sqlite = True
        raw_path = db_url.replace("sqlite:///", "").replace("sqlite://", "")
        if not raw_path or raw_path == ":memory:":
            _sqlite_path = "file:agentic_test_shared?mode=memory&cache=shared"
        else:
            _sqlite_path = raw_path

        with _sqlite_write_lock:
            conn = _get_sqlite_connection()
            conn._conn.executescript(SQLITE_SCHEMA_SQL)
        logger.info("SQLite Database initialized successfully at %s", _sqlite_path)
        return

    # PostgreSQL path
    _is_sqlite = False
    try:
        from psycopg_pool import ConnectionPool
        from psycopg.rows import dict_row

        if not _pool:
            _pool = ConnectionPool(
                db_url,
                min_size=1,
                max_size=20,
                kwargs={"row_factory": dict_row}
            )

        last_err = None
        for attempt in range(1, max_retries + 1):
            try:
                with _pool.connection(timeout=3.0) as conn:
                    with conn.cursor() as cur:
                        cur.execute(POSTGRES_SCHEMA_SQL)
                    conn.commit()
                logger.info("PostgreSQL Database initialized successfully")
                return
            except Exception as exc:
                last_err = exc
                logger.warning(f"Database connection attempt {attempt}/{max_retries} failed: {exc}")
                if attempt < max_retries:
                    import time
                    time.sleep(retry_delay)

        # If PostgreSQL failed in test/development mode, gracefully fallback to SQLite
        if settings.app_env.lower() in ("test", "testing", "development", "dev"):
            logger.warning("PostgreSQL unreachable in %s mode; falling back to SQLite shared memory database.", settings.app_env)
            _is_sqlite = True
            _sqlite_path = "file:agentic_test_shared?mode=memory&cache=shared"
            with _sqlite_write_lock:
                conn = _get_sqlite_connection()
                conn._conn.executescript(SQLITE_SCHEMA_SQL)
            return

        if last_err:
            raise last_err

    except ImportError:
        logger.warning("psycopg_pool not available; using SQLite.")
        _is_sqlite = True
        _sqlite_path = "file:agentic_test_shared?mode=memory&cache=shared"
        with _sqlite_write_lock:
            conn = _get_sqlite_connection()
            conn._conn.executescript(SQLITE_SCHEMA_SQL)


def close_db() -> None:
    """Close connection pool or SQLite connection."""
    global _pool
    if _pool:
        _pool.close()
        _pool = None
        logger.info("PostgreSQL Database connection pool closed")
    if hasattr(_local, "conn") and _local.conn is not None:
        try:
            _local.conn.close()
        except Exception:
            pass
        _local.conn = None


@contextmanager
def get_db() -> Generator[Any, None, None]:
    """Context manager for database connections."""
    global _pool, _is_sqlite
    if _is_sqlite:
        with _sqlite_write_lock:
            yield _get_sqlite_connection()
        return

    if not _pool:
        init_db()

    with _pool.connection() as conn:
        yield conn


@contextmanager
def get_db_transaction() -> Generator[Any, None, None]:
    """Context manager for write transactions."""
    global _pool, _is_sqlite
    if _is_sqlite:
        conn = _get_sqlite_connection()
        with conn.transaction():
            yield conn
        return

    if not _pool:
        init_db()

    with _pool.connection() as conn:
        try:
            with conn.transaction():
                yield conn
        except Exception:
            raise
