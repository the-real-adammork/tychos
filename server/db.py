"""Postgres database connection and schema management.

Migrations are numbered SQL files in server/migrations/pg/.
A _migrations table tracks which have been applied.
"""
import os
from pathlib import Path
from contextlib import contextmanager, asynccontextmanager

import numpy as np
import psycopg2
import psycopg2.extras
import psycopg2.extensions
import psycopg2.pool
import asyncpg

DATABASE_URL = os.environ.get("DATABASE_URL", "")
MIGRATIONS_DIR = Path(__file__).parent / "migrations" / "pg"


# Teach psycopg2 how to adapt numpy scalars produced by the scanner.
def _adapt_np_floating(x):
    return psycopg2.extensions.AsIs(repr(float(x)))


def _adapt_np_integer(x):
    return psycopg2.extensions.AsIs(repr(int(x)))


def _adapt_np_bool(x):
    return psycopg2.extensions.AsIs("TRUE" if bool(x) else "FALSE")


for _t in (np.float64, np.float32, np.float16):
    psycopg2.extensions.register_adapter(_t, _adapt_np_floating)
for _t in (np.int64, np.int32, np.int16, np.int8):
    psycopg2.extensions.register_adapter(_t, _adapt_np_integer)
psycopg2.extensions.register_adapter(np.bool_, _adapt_np_bool)

_sync_pool: psycopg2.pool.SimpleConnectionPool | None = None
_async_pool: "asyncpg.Pool | None" = None


def _ensure_sync_pool() -> psycopg2.pool.SimpleConnectionPool:
    global _sync_pool
    if _sync_pool is None:
        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL env var is not set")
        _sync_pool = psycopg2.pool.SimpleConnectionPool(1, 5, dsn=DATABASE_URL)
    return _sync_pool


async def _ensure_async_pool() -> "asyncpg.Pool":
    global _async_pool
    if _async_pool is None:
        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL env var is not set")
        _async_pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)
    return _async_pool


def init_db():
    """Apply any unapplied migrations, then run seed."""
    _run_migrations()
    from server.seed import seed
    seed()


def _run_migrations():
    pool = _ensure_sync_pool()
    conn = pool.getconn()
    try:
        conn.autocommit = False
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS _migrations (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
            """)
            conn.commit()
            cur.execute("SELECT name FROM _migrations")
            applied = {row[0] for row in cur.fetchall()}

        for migration_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
            name = migration_file.name
            if name in applied:
                continue
            print(f"[db] Applying migration: {name}")
            sql = migration_file.read_text()
            with conn.cursor() as cur:
                cur.execute(sql)
                cur.execute("INSERT INTO _migrations (name) VALUES (%s)", (name,))
            conn.commit()
    finally:
        pool.putconn(conn)


@contextmanager
def get_db():
    """Yield a sync psycopg2 connection with DictCursor rows."""
    pool = _ensure_sync_pool()
    conn = pool.getconn()
    conn.cursor_factory = psycopg2.extras.DictCursor
    try:
        yield conn
    finally:
        pool.putconn(conn)


@asynccontextmanager
async def get_async_db():
    """Yield an asyncpg connection from the pool."""
    pool = await _ensure_async_pool()
    async with pool.acquire() as conn:
        yield conn
