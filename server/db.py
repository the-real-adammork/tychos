"""SQLite database connection and schema management via migrations.

Migrations are numbered SQL files in server/migrations/.
A _migrations table tracks which have been applied.
"""
import sqlite3
from pathlib import Path
from contextlib import contextmanager, asynccontextmanager

import aiosqlite

DB_PATH = Path(__file__).parent.parent / "results" / "tychos_results.db"
MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def init_db():
    """Apply any unapplied migrations, then run seed. Creates the db file if needed."""
    _run_migrations()
    _run_seed()


def _run_migrations():
    """Apply any unapplied SQL migrations."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS _migrations (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()

    applied = {row[0] for row in conn.execute("SELECT name FROM _migrations").fetchall()}

    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    for migration_file in migration_files:
        name = migration_file.name
        if name in applied:
            continue
        print(f"[db] Applying migration: {name}")
        sql = migration_file.read_text()
        conn.executescript(sql)
        conn.execute("INSERT INTO _migrations (name) VALUES (?)", (name,))
        conn.commit()

    conn.close()


def _run_seed():
    """Run the seed script (idempotent)."""
    from server.seed import seed
    seed()


# --- Sync access (used by worker process) ---

@contextmanager
def get_db():
    """Yield a sync sqlite3 connection with row_factory set to Row."""
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


# --- Async access (used by API server) ---

@asynccontextmanager
async def get_async_db():
    """Yield an async aiosqlite connection with row_factory set to Row."""
    conn = await aiosqlite.connect(str(DB_PATH), timeout=10)
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        await conn.close()
