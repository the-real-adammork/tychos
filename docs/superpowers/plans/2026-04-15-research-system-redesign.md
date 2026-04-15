# Research System Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the filesystem-based research loop with a Postgres-backed, DB-driven architecture where the AI researcher creates param versions through the API, the existing worker executes scans via LISTEN/NOTIFY, and results flow through SQL views.

**Architecture:** Migrate SQLite → Postgres (consolidated initial schema). Add `research_jobs` / `research_iterations` tables, `is_checkpoint` on `param_versions`, and optional `date_start`/`date_end` on `runs`. Expose SQL views (`v_solar_position`, `v_moon_position`, `v_combined_position`) that the view API endpoint queries per run. Worker subscribes to `LISTEN run_queued` with a 5s fallback poll; trigger fires `NOTIFY run_status_changed` on completion. Research endpoints (CRUD, iterations, checkpoint/restore, allowlist-validated version create, server-side Nelder-Mead) live under `/api/research/*`. Delete the entire `server/research/cli.py`/`sandbox.py`/`subset.py`/`program_md.py`/`allowlist.py`/`objective.py`/`search.py` filesystem stack once the new path is green.

**Tech Stack:** Postgres 15+, asyncpg (async API), psycopg2-binary (sync worker), FastAPI, pytest, scipy.optimize.minimize (Nelder-Mead, already a transitive dep).

---

## File Structure

**Created:**
- `server/migrations/pg/001_initial.sql` — consolidated Postgres initial schema (tables from 13 SQLite migrations)
- `server/migrations/pg/002_research.sql` — `research_jobs`, `research_iterations`, `is_checkpoint`, `runs.date_start/date_end`
- `server/migrations/pg/003_views.sql` — `v_solar_position`, `v_moon_position`, `v_combined_position`
- `server/migrations/pg/004_notify.sql` — LISTEN/NOTIFY trigger functions + triggers
- `server/api/research_routes.py` — research CRUD + iterations + checkpoint/restore + version + search
- `server/api/views_routes.py` — `GET /api/results/{run_id}/view/{view_name}`
- `server/research/instructions.py` — renders the `instructions` field from a Jinja-free string template
- `server/research/templates/instructions.md.tmpl` — repurposed from the existing `program.md.tmpl`
- `server/research/allowlist.py` — ONLY `expand_globs` + `check_diff_against_allowlist` kept (rewritten stand-alone); other research files deleted
- `server/research/search_engine.py` — Nelder-Mead engine callable from the search endpoint
- `tests/test_db_pg.py` — migration + connection smoke test
- `tests/api/test_views.py` — view endpoint integration tests
- `tests/api/test_research_crud.py`
- `tests/api/test_research_version.py` — allowlist validation
- `tests/api/test_research_iterations.py` — checkpoint, restore
- `tests/api/test_research_search.py` — Nelder-Mead endpoint
- `tests/test_worker_notify.py` — LISTEN/NOTIFY timing
- `tests/test_research_e2e.py` — full flow

**Modified:**
- `server/db.py` — asyncpg + psycopg2 pools, new migration runner
- `server/worker.py` — psycopg2, LISTEN/NOTIFY, date-filtered catalog, new placeholders
- `server/seed.py` — psycopg2 placeholders, `ON CONFLICT DO NOTHING`
- `server/app.py` — register `research_router`, `views_router`
- `server/api/auth_routes.py`, `params_routes.py`, `runs_routes.py`, `results_routes.py`, `compare_routes.py`, `dashboard_routes.py`, `dataset_routes.py` — `?` → `$1`, `INSERT OR IGNORE` → `ON CONFLICT DO NOTHING`, `lastrowid` → `RETURNING id`
- `server/auth.py` — asyncpg rows
- `requirements.txt` — add `asyncpg`, `psycopg2-binary`; remove `aiosqlite`
- `start-server.sh`, `start-worker.sh` — `DATABASE_URL` env var
- `local_deploy/.env.example` — `DATABASE_URL`
- `tests/conftest.py` — Postgres test DB fixture

**Deleted:**
- `server/research/cli.py`
- `server/research/__main__.py`
- `server/research/sandbox.py`
- `server/research/subset.py`
- `server/research/program_md.py`
- `server/research/objective.py`
- `server/research/search.py`
- `server/research/templates/program.md.tmpl` (replaced by `instructions.md.tmpl`)
- `research.sh`
- `params/research/` (entire directory)
- `tests/research/test_sandbox.py`
- `tests/research/test_subset.py`
- `tests/research/test_program_md.py`
- `tests/research/test_objective.py`
- `tests/research/test_smoke.py`
- `tests/research/conftest.py`
- `tests/research/test_allowlist.py` replaced by API-integration allowlist test

---

## Task 1: Add Postgres dependencies and configuration

**Files:**
- Modify: `requirements.txt`
- Modify: `start-server.sh`
- Modify: `start-worker.sh`
- Modify: `local_deploy/.env.example`

- [ ] **Step 1: Update requirements.txt**

Replace file contents:
```
numpy
scipy
pytest
pytest-asyncio
fastapi
uvicorn[standard]
pydantic
bcrypt
asyncpg
psycopg2-binary
httpx
```

- [ ] **Step 2: Update start-server.sh**

```bash
#!/bin/bash
cd "$(dirname "$0")"
source tychos_skyfield/.venv/bin/activate
: "${DATABASE_URL:?DATABASE_URL not set (e.g. postgres://tychos:tychos@localhost:5432/tychos)}"
PYTHONPATH=tychos_skyfield:tests:. exec uvicorn server.app:app --port 8000 --reload
```

- [ ] **Step 3: Update start-worker.sh**

```bash
#!/bin/bash
cd "$(dirname "$0")"
source tychos_skyfield/.venv/bin/activate
: "${DATABASE_URL:?DATABASE_URL not set}"
PYTHONPATH=tychos_skyfield:tests:. exec python -m server.worker
```

- [ ] **Step 4: Update local_deploy/.env.example**

Append:
```
# Postgres
DATABASE_URL=postgres://tychos:tychos@localhost:5432/tychos
```

- [ ] **Step 5: Install deps**

Run: `source tychos_skyfield/.venv/bin/activate && pip install -r requirements.txt`
Expected: installs complete with no errors.

- [ ] **Step 6: Provision a local Postgres**

Run (once, outside Python):
```bash
brew install postgresql@15 || true
brew services start postgresql@15
createuser -s tychos 2>/dev/null || true
createdb -O tychos tychos 2>/dev/null || true
psql -d tychos -c "ALTER USER tychos WITH PASSWORD 'tychos';"
```
Expected: `psql postgres://tychos:tychos@localhost:5432/tychos -c 'SELECT 1'` returns `1`.

- [ ] **Step 7: Commit**

```bash
git add requirements.txt start-server.sh start-worker.sh local_deploy/.env.example
git commit -m "chore: add postgres deps and DATABASE_URL plumbing"
```

---

## Task 2: Consolidated Postgres initial schema

**Files:**
- Create: `server/migrations/pg/001_initial.sql`

This file collapses SQLite migrations 001–013 into one Postgres-native schema. `AUTOINCREMENT` → `GENERATED ALWAYS AS IDENTITY`, `REAL` → `DOUBLE PRECISION`, text dates stay `TEXT`, booleans use `BOOLEAN`.

- [ ] **Step 1: Write `server/migrations/pg/001_initial.sql`**

```sql
CREATE TABLE users (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS'))
);

CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at TEXT NOT NULL
);

CREATE TABLE datasets (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    event_type TEXT NOT NULL,
    source_url TEXT,
    description TEXT,
    record_count INTEGER NOT NULL DEFAULT 0,
    scan_window_hours DOUBLE PRECISION NOT NULL DEFAULT 6.0,
    created_at TEXT NOT NULL DEFAULT (to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS'))
);

INSERT INTO datasets (slug, name, event_type, source_url, description) VALUES
    ('solar_eclipse', 'NASA Solar Eclipses', 'solar_eclipse',
     'https://eclipse.gsfc.nasa.gov/SEcat5/',
     'Five Millennium Canon of Solar Eclipses (1901-2100)'),
    ('lunar_eclipse', 'NASA Lunar Eclipses', 'lunar_eclipse',
     'https://eclipse.gsfc.nasa.gov/LEcat5/',
     'Five Millennium Canon of Lunar Eclipses (1901-2100)');

CREATE TABLE param_sets (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    forked_from_id INTEGER REFERENCES param_sets(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT (to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS'))
);

CREATE TABLE param_versions (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    param_set_id INTEGER NOT NULL REFERENCES param_sets(id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL DEFAULT 1,
    parent_version_id INTEGER REFERENCES param_versions(id) ON DELETE SET NULL,
    params_md5 TEXT NOT NULL,
    params_json TEXT NOT NULL,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS'))
);

CREATE TABLE runs (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    param_version_id INTEGER NOT NULL REFERENCES param_versions(id) ON DELETE CASCADE,
    dataset_id INTEGER NOT NULL REFERENCES datasets(id),
    status TEXT NOT NULL DEFAULT 'queued',
    code_version TEXT NOT NULL DEFAULT '1.0',
    tsn_commit TEXT,
    skyfield_commit TEXT,
    total_eclipses INTEGER,
    detected INTEGER,
    mean_sun_diff DOUBLE PRECISION,
    mean_moon_diff DOUBLE PRECISION,
    mean_timing_offset DOUBLE PRECISION,
    created_at TEXT NOT NULL DEFAULT (to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS')),
    started_at TEXT,
    completed_at TEXT,
    error TEXT
);

CREATE INDEX idx_runs_status_created ON runs(status, created_at);

CREATE TABLE eclipse_catalog (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    dataset_id INTEGER NOT NULL REFERENCES datasets(id),
    catalog_number TEXT NOT NULL,
    julian_day_tt DOUBLE PRECISION NOT NULL,
    date TEXT NOT NULL,
    delta_t_s INTEGER,
    luna_num INTEGER,
    saros_num INTEGER,
    type_raw TEXT NOT NULL,
    type TEXT NOT NULL,
    gamma DOUBLE PRECISION,
    magnitude DOUBLE PRECISION NOT NULL,
    qle TEXT,
    lat INTEGER,
    lon INTEGER,
    sun_alt_deg INTEGER,
    path_width_km INTEGER,
    duration_s INTEGER,
    qse TEXT,
    pen_mag DOUBLE PRECISION,
    um_mag DOUBLE PRECISION,
    pen_duration_min DOUBLE PRECISION,
    par_duration_min DOUBLE PRECISION,
    total_duration_min DOUBLE PRECISION,
    zenith_lat INTEGER,
    zenith_lon INTEGER
);
CREATE UNIQUE INDEX idx_eclipse_catalog_dataset_jd ON eclipse_catalog(dataset_id, julian_day_tt);
CREATE INDEX idx_eclipse_catalog_dataset_type ON eclipse_catalog(dataset_id, type);

CREATE TABLE jpl_reference (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    dataset_id INTEGER NOT NULL REFERENCES datasets(id),
    julian_day_tt DOUBLE PRECISION NOT NULL,
    sun_ra_rad DOUBLE PRECISION NOT NULL,
    sun_dec_rad DOUBLE PRECISION NOT NULL,
    moon_ra_rad DOUBLE PRECISION NOT NULL,
    moon_dec_rad DOUBLE PRECISION NOT NULL,
    separation_arcmin DOUBLE PRECISION NOT NULL,
    moon_ra_vel DOUBLE PRECISION,
    moon_dec_vel DOUBLE PRECISION,
    best_jd DOUBLE PRECISION,
    sun_ra_at_best_rad DOUBLE PRECISION,
    sun_dec_at_best_rad DOUBLE PRECISION,
    moon_ra_at_best_rad DOUBLE PRECISION,
    moon_dec_at_best_rad DOUBLE PRECISION
);
CREATE UNIQUE INDEX idx_jpl_reference_dataset_jd ON jpl_reference(dataset_id, julian_day_tt);

CREATE TABLE predicted_reference (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    julian_day_tt DOUBLE PRECISION NOT NULL,
    test_type TEXT NOT NULL,
    expected_separation_arcmin DOUBLE PRECISION NOT NULL,
    moon_apparent_radius_arcmin DOUBLE PRECISION NOT NULL,
    sun_apparent_radius_arcmin DOUBLE PRECISION,
    umbra_radius_arcmin DOUBLE PRECISION,
    penumbra_radius_arcmin DOUBLE PRECISION,
    approach_angle_deg DOUBLE PRECISION,
    gamma DOUBLE PRECISION NOT NULL,
    catalog_magnitude DOUBLE PRECISION NOT NULL,
    UNIQUE(julian_day_tt, test_type)
);

CREATE TABLE eclipse_results (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    julian_day_tt DOUBLE PRECISION NOT NULL,
    date TEXT NOT NULL,
    catalog_type TEXT NOT NULL,
    magnitude DOUBLE PRECISION NOT NULL,
    detected BOOLEAN NOT NULL,
    threshold_arcmin DOUBLE PRECISION NOT NULL,
    min_separation_arcmin DOUBLE PRECISION,
    timing_offset_min DOUBLE PRECISION,
    best_jd DOUBLE PRECISION,
    sun_ra_rad DOUBLE PRECISION,
    sun_dec_rad DOUBLE PRECISION,
    moon_ra_rad DOUBLE PRECISION,
    moon_dec_rad DOUBLE PRECISION,
    moon_error_arcmin DOUBLE PRECISION,
    moon_ra_vel DOUBLE PRECISION,
    moon_dec_vel DOUBLE PRECISION,
    tychos_error_arcmin DOUBLE PRECISION,
    jpl_error_arcmin DOUBLE PRECISION,
    jpl_timing_offset_min DOUBLE PRECISION,
    sun_delta_ra_arcmin DOUBLE PRECISION,
    sun_delta_dec_arcmin DOUBLE PRECISION,
    moon_delta_ra_arcmin DOUBLE PRECISION,
    moon_delta_dec_arcmin DOUBLE PRECISION,
    tychos_sun_ra_at_jpl_rad DOUBLE PRECISION,
    tychos_sun_dec_at_jpl_rad DOUBLE PRECISION,
    tychos_moon_ra_at_jpl_rad DOUBLE PRECISION,
    tychos_moon_dec_at_jpl_rad DOUBLE PRECISION
);

CREATE INDEX idx_eclipse_results_run ON eclipse_results(run_id);
CREATE INDEX idx_eclipse_results_run_date ON eclipse_results(run_id, date);
```

- [ ] **Step 2: Commit**

```bash
git add server/migrations/pg/001_initial.sql
git commit -m "feat(db): add consolidated postgres initial schema"
```

---

## Task 3: Research tables migration

**Files:**
- Create: `server/migrations/pg/002_research.sql`

- [ ] **Step 1: Write `server/migrations/pg/002_research.sql`**

```sql
ALTER TABLE param_versions
    ADD COLUMN is_checkpoint BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE runs ADD COLUMN date_start TEXT;
ALTER TABLE runs ADD COLUMN date_end TEXT;

CREATE TABLE research_jobs (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL,
    param_set_id INTEGER NOT NULL REFERENCES param_sets(id),
    dataset_id INTEGER NOT NULL REFERENCES datasets(id),
    view_name TEXT NOT NULL,
    allowlist TEXT[] NOT NULL,
    date_start TEXT,
    date_end TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    instructions TEXT,
    created_at TEXT NOT NULL DEFAULT (to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS')),
    updated_at TEXT
);

CREATE INDEX idx_research_jobs_status ON research_jobs(status);

CREATE TABLE research_iterations (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    research_job_id INTEGER NOT NULL REFERENCES research_jobs(id) ON DELETE CASCADE,
    param_version_id INTEGER NOT NULL REFERENCES param_versions(id),
    run_id INTEGER REFERENCES runs(id),
    kind TEXT NOT NULL,
    objective DOUBLE PRECISION,
    aux_stats JSONB,
    created_at TEXT NOT NULL DEFAULT (to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS'))
);

CREATE INDEX idx_research_iterations_job ON research_iterations(research_job_id, created_at);
```

- [ ] **Step 2: Commit**

```bash
git add server/migrations/pg/002_research.sql
git commit -m "feat(db): add research_jobs and research_iterations tables"
```

---

## Task 4: SQL views migration

**Files:**
- Create: `server/migrations/pg/003_views.sql`

- [ ] **Step 1: Write `server/migrations/pg/003_views.sql`**

```sql
CREATE VIEW v_solar_position AS
SELECT run_id, julian_day_tt, date, catalog_type,
       sun_delta_ra_arcmin, sun_delta_dec_arcmin,
       sqrt(sun_delta_ra_arcmin^2 + sun_delta_dec_arcmin^2) AS error
  FROM eclipse_results
 WHERE sun_delta_ra_arcmin IS NOT NULL;

CREATE VIEW v_moon_position AS
SELECT run_id, julian_day_tt, date, catalog_type,
       moon_delta_ra_arcmin, moon_delta_dec_arcmin,
       sqrt(moon_delta_ra_arcmin^2 + moon_delta_dec_arcmin^2) AS error
  FROM eclipse_results
 WHERE moon_delta_ra_arcmin IS NOT NULL;

CREATE VIEW v_combined_position AS
SELECT run_id, julian_day_tt, date, catalog_type,
       sun_delta_ra_arcmin, sun_delta_dec_arcmin,
       moon_delta_ra_arcmin, moon_delta_dec_arcmin,
       sqrt(sun_delta_ra_arcmin^2 + sun_delta_dec_arcmin^2
          + moon_delta_ra_arcmin^2 + moon_delta_dec_arcmin^2) AS error
  FROM eclipse_results
 WHERE sun_delta_ra_arcmin IS NOT NULL
   AND moon_delta_ra_arcmin IS NOT NULL;
```

- [ ] **Step 2: Commit**

```bash
git add server/migrations/pg/003_views.sql
git commit -m "feat(db): add per-objective result views"
```

---

## Task 5: LISTEN/NOTIFY triggers migration

**Files:**
- Create: `server/migrations/pg/004_notify.sql`

- [ ] **Step 1: Write `server/migrations/pg/004_notify.sql`**

```sql
CREATE OR REPLACE FUNCTION notify_run_queued() RETURNS trigger AS $$
BEGIN
    IF NEW.status = 'queued' AND (TG_OP = 'INSERT' OR OLD.status IS DISTINCT FROM NEW.status) THEN
        PERFORM pg_notify('run_queued', NEW.id::text);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_run_queued
    AFTER INSERT OR UPDATE ON runs
    FOR EACH ROW EXECUTE FUNCTION notify_run_queued();

CREATE OR REPLACE FUNCTION notify_run_completed() RETURNS trigger AS $$
BEGIN
    IF NEW.status IN ('done', 'failed')
       AND (OLD.status IS NULL OR OLD.status IS DISTINCT FROM NEW.status) THEN
        PERFORM pg_notify('run_status_changed',
            json_build_object('run_id', NEW.id, 'status', NEW.status)::text);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_run_completed
    AFTER UPDATE ON runs
    FOR EACH ROW EXECUTE FUNCTION notify_run_completed();
```

- [ ] **Step 2: Commit**

```bash
git add server/migrations/pg/004_notify.sql
git commit -m "feat(db): add LISTEN/NOTIFY triggers for run status"
```

---

## Task 6: Rewrite `server/db.py` for Postgres

**Files:**
- Modify: `server/db.py` (full rewrite)
- Create: `tests/test_db_pg.py`

- [ ] **Step 1: Write the failing test `tests/test_db_pg.py`**

```python
import os
import asyncio
import pytest

from server.db import init_db, get_db, get_async_db, DATABASE_URL


def test_database_url_configured():
    assert DATABASE_URL, "DATABASE_URL env var must be set for the test DB"


def test_init_db_creates_tables_and_views():
    init_db()
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT to_regclass('public.users')")
        assert cur.fetchone()[0] == "users"
        cur.execute("SELECT to_regclass('public.research_jobs')")
        assert cur.fetchone()[0] == "research_jobs"
        cur.execute("SELECT to_regclass('public.v_solar_position')")
        assert cur.fetchone()[0] == "v_solar_position"


def test_async_db_roundtrip():
    async def go():
        async with get_async_db() as conn:
            row = await conn.fetchrow("SELECT 1 AS n")
            assert row["n"] == 1
    asyncio.run(go())
```

- [ ] **Step 2: Run the test — expect ImportError/fail**

Run: `TYCHOS_ADMIN_USER=admin@t.local TYCHOS_ADMIN_PASSWORD=pw DATABASE_URL=postgres://tychos:tychos@localhost:5432/tychos_test PYTHONPATH=tychos_skyfield:tests:. pytest tests/test_db_pg.py -v`
Expected: FAIL (current db.py uses sqlite3/aiosqlite).

- [ ] **Step 3: Replace `server/db.py`**

```python
"""Postgres database connection and schema management.

Migrations are numbered SQL files in server/migrations/pg/.
A _migrations table tracks which have been applied.
"""
import os
from pathlib import Path
from contextlib import contextmanager, asynccontextmanager

import psycopg2
import psycopg2.extras
import psycopg2.pool
import asyncpg

DATABASE_URL = os.environ.get("DATABASE_URL", "")
MIGRATIONS_DIR = Path(__file__).parent / "migrations" / "pg"

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
```

- [ ] **Step 4: Run the test — expect PASS**

First create the test DB: `createdb -O tychos tychos_test 2>/dev/null || true`.
Run: `TYCHOS_ADMIN_USER=admin@t.local TYCHOS_ADMIN_PASSWORD=pw DATABASE_URL=postgres://tychos:tychos@localhost:5432/tychos_test PYTHONPATH=tychos_skyfield:tests:. pytest tests/test_db_pg.py -v`
Expected: first test PASS; `test_init_db_creates_tables_and_views` may fail if seed is still sqlite — that's OK for now, it's fixed in Task 7.

- [ ] **Step 5: Commit**

```bash
git add server/db.py tests/test_db_pg.py
git commit -m "feat(db): rewrite db module on top of asyncpg and psycopg2"
```

---

## Task 7: Port `server/seed.py` to Postgres

**Files:**
- Modify: `server/seed.py`

The seed logic is identical; only placeholders, `INSERT OR IGNORE`, and `cur.lastrowid` semantics change.

- [ ] **Step 1: Replace all SQLite-specific calls**

In `server/seed.py`, apply these global rewrites:
- `import sqlite3` → remove (use `psycopg2.errors.UniqueViolation`)
- `conn.execute(...)` → `with conn.cursor() as cur: cur.execute(...)` (wrap each call)
- `?` → `%s` in every SQL literal
- `INSERT OR IGNORE` → `INSERT ... ON CONFLICT DO NOTHING`
- `cur.lastrowid` → `cur.fetchone()[0]` after appending `RETURNING id` to inserts that need the id
- `except sqlite3.IntegrityError` → `except psycopg2.errors.UniqueViolation`

The cleanest approach is a full rewrite. Use the existing file structure but replace the SQL-executing bodies. Pseudocode for the inserts that need an id:
```python
with conn.cursor() as cur:
    cur.execute(
        "INSERT INTO param_sets (name, description, owner_id, forked_from_id) "
        "VALUES (%s,%s,%s,%s) RETURNING id",
        (ps["name"], ps.get("description"), user["id"], forked_from_id),
    )
    param_set_id = cur.fetchone()[0]
conn.commit()
```

Every `conn.execute`/`conn.executemany` becomes `with conn.cursor() as cur: cur.execute(...)` (or `cur.executemany(...)`). Every existing `conn.commit()` call stays.

Also replace every `SELECT ... LIMIT 1` fetch that used `fetchone()["col"]` — `DictCursor` already returns subscriptable rows, so no change needed at call sites.

- [ ] **Step 2: Verify seed runs end-to-end**

Run:
```bash
createdb -O tychos tychos_test 2>/dev/null || true
psql postgres://tychos:tychos@localhost:5432/tychos_test -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
TYCHOS_ADMIN_USER=admin@t.local TYCHOS_ADMIN_PASSWORD=pw DATABASE_URL=postgres://tychos:tychos@localhost:5432/tychos_test PYTHONPATH=tychos_skyfield:tests:. python -c "from server.db import init_db; init_db()"
```
Expected: runs without error, prints `[seed] Created ...` and `[seed] Loaded ... eclipse catalog entries`.

- [ ] **Step 3: Spot-check with SQL**

Run: `psql postgres://tychos:tychos@localhost:5432/tychos_test -c "SELECT count(*) FROM eclipse_catalog; SELECT count(*) FROM param_sets; SELECT count(*) FROM runs;"`
Expected: non-zero counts matching the SQLite baseline.

- [ ] **Step 4: Commit**

```bash
git add server/seed.py
git commit -m "feat(db): port seed to postgres"
```

---

## Task 8: Port API route modules to asyncpg

**Files:**
- Modify: `server/api/auth_routes.py`
- Modify: `server/api/params_routes.py`
- Modify: `server/api/runs_routes.py`
- Modify: `server/api/results_routes.py`
- Modify: `server/api/compare_routes.py`
- Modify: `server/api/dashboard_routes.py`
- Modify: `server/api/dataset_routes.py`
- Modify: `server/auth.py`

asyncpg exposes a slightly different API than aiosqlite:
- `conn.execute("SQL", arg1, arg2)` — positional args (no tuple)
- `conn.fetch("SQL", ...)` — returns list of `Record` (dict-like)
- `conn.fetchrow("SQL", ...)` — returns one `Record` or None
- `conn.fetchval("SQL", ...)` — returns a single scalar or None
- Placeholders are `$1, $2, ...`
- `RETURNING id` is how you get the new row id (no `lastrowid`)
- `cursor.lastrowid` does not exist — use `fetchval` with `RETURNING`
- No `conn.commit()` needed (auto-commit per statement unless `async with conn.transaction()`)

- [ ] **Step 1: Port `server/auth.py`**

Replace every occurrence of:
```python
cursor = await conn.execute("SELECT ... WHERE ... = ?", (value,))
row = await cursor.fetchone()
```
with:
```python
row = await conn.fetchrow("SELECT ... WHERE ... = $1", value)
```

- [ ] **Step 2: Port `server/api/params_routes.py`**

Apply the same transformation rule file-wide, plus:
- `await conn.commit()` → remove
- `pv_cursor.lastrowid` → use `RETURNING id` + `fetchval`: 
  ```python
  param_version_id = await conn.fetchval(
      "INSERT INTO param_versions (param_set_id, version_number, params_md5, params_json, notes) "
      "VALUES ($1,$2,$3,$4,$5) RETURNING id",
      param_set_id, 1, params_md5, body.params_json, body.notes,
  )
  ```
- Multi-statement composition (e.g., update + commit + insert) should wrap in `async with conn.transaction():` only when atomicity is needed.
- `auto_queue_runs(conn, pv_id)` rewrite:
  ```python
  async def auto_queue_runs(conn, param_version_id: int, date_start: str | None = None, date_end: str | None = None):
      ds_rows = await conn.fetch("SELECT id FROM datasets ORDER BY id")
      for ds in ds_rows:
          await conn.execute(
              "INSERT INTO runs (param_version_id, dataset_id, status, date_start, date_end) "
              "VALUES ($1,$2,'queued',$3,$4)",
              param_version_id, ds["id"], date_start, date_end,
          )
  ```
  Added `date_start`/`date_end` kwargs so research can pass them through.

- [ ] **Step 3: Port `server/api/runs_routes.py`**

Same rule set. `cursor.lastrowid` → `RETURNING id`. Row dicts already work with asyncpg `Record`; keep `dict(row)` in `_row_to_dict`.

- [ ] **Step 4: Port `server/api/results_routes.py`**

The parameterized `WHERE` clauses here are built dynamically. Change the placeholder generator from `"?"` to `f"${i}"` with an incrementing counter; collect args positionally.

- [ ] **Step 5: Port remaining route modules**

Apply the same rule set to `compare_routes.py`, `dashboard_routes.py`, `dataset_routes.py`.

- [ ] **Step 6: Run the existing API tests against Postgres**

Run: `TYCHOS_ADMIN_USER=admin@t.local TYCHOS_ADMIN_PASSWORD=pw DATABASE_URL=postgres://tychos:tychos@localhost:5432/tychos_test PYTHONPATH=tychos_skyfield:tests:. pytest tests/ -x -k "not research" -v`
Expected: all non-research tests pass.

- [ ] **Step 7: Commit**

```bash
git add server/api/ server/auth.py
git commit -m "feat(api): port all routes to asyncpg"
```

---

## Task 9: Port worker to psycopg2 + LISTEN/NOTIFY

**Files:**
- Modify: `server/worker.py`
- Create: `tests/test_worker_notify.py`

- [ ] **Step 1: Write the failing test `tests/test_worker_notify.py`**

```python
import os
import threading
import time
import pytest
import psycopg2

from server.db import init_db, get_db, DATABASE_URL
from server.worker import _worker_loop, _process_one  # noqa


def test_listen_wakes_worker_before_poll_interval(monkeypatch):
    """When a run is INSERT'd with status='queued', the worker's select() returns
    via NOTIFY in well under the 5s poll fallback."""
    init_db()
    # Seed: get any existing param_version + dataset
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM param_versions ORDER BY id LIMIT 1")
            pv_id = cur.fetchone()[0]
            cur.execute("SELECT id FROM datasets ORDER BY id LIMIT 1")
            ds_id = cur.fetchone()[0]

    # Manually LISTEN from a fresh connection to verify the trigger fires
    conn = psycopg2.connect(DATABASE_URL)
    conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
    with conn.cursor() as cur:
        cur.execute("LISTEN run_queued")

    with get_db() as ins_conn:
        with ins_conn.cursor() as cur:
            cur.execute(
                "INSERT INTO runs (param_version_id, dataset_id, status) VALUES (%s,%s,'queued') RETURNING id",
                (pv_id, ds_id),
            )
            new_run_id = cur.fetchone()[0]
        ins_conn.commit()

    import select
    if select.select([conn], [], [], 2.0) == ([], [], []):
        pytest.fail("Expected NOTIFY within 2s of insert")
    conn.poll()
    assert conn.notifies, "No notifies received"
    assert conn.notifies[0].channel == "run_queued"
    assert int(conn.notifies[0].payload) == new_run_id
```

- [ ] **Step 2: Run test — expect fail** (worker + migrations not yet wired)

Run: `TYCHOS_ADMIN_USER=admin@t.local TYCHOS_ADMIN_PASSWORD=pw DATABASE_URL=postgres://tychos:tychos@localhost:5432/tychos_test PYTHONPATH=tychos_skyfield:tests:. pytest tests/test_worker_notify.py -v`
Expected: FAIL — worker.py still imports sqlite get_db.

- [ ] **Step 3: Rewrite `server/worker.py`**

Preserve all scanner + enrichment logic untouched. Replace DB layer with psycopg2, add LISTEN/NOTIFY loop, support date-filtered catalog:

```python
"""Background worker that processes queued eclipse runs (Postgres)."""
import json
import math
import os
import select
import time
import threading
import traceback
from datetime import datetime, timezone

import psycopg2
import psycopg2.extensions

from server.db import get_db, DATABASE_URL
from server.services.scanner import (
    load_eclipse_catalog,
    scan_solar_eclipses,
    scan_lunar_eclipses,
)

_POLL_INTERVAL = 5.0


def start_worker() -> threading.Thread:
    t = threading.Thread(target=_worker_loop, daemon=True, name="eclipse-worker")
    t.start()
    return t


def _worker_loop() -> None:
    listen_conn = psycopg2.connect(DATABASE_URL)
    listen_conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
    with listen_conn.cursor() as cur:
        cur.execute("LISTEN run_queued")

    while True:
        try:
            # Drain anything queued before we started listening.
            _process_all_queued()

            # Wait for the next NOTIFY or a poll-interval timeout.
            if select.select([listen_conn], [], [], _POLL_INTERVAL) == ([], [], []):
                pass  # timeout — fall through to poll
            listen_conn.poll()
            while listen_conn.notifies:
                listen_conn.notifies.pop(0)  # drain; _process_all_queued handles the row
        except Exception:
            print(f"[worker] Unexpected loop error:\n{traceback.format_exc()}")
            time.sleep(1.0)


def _process_all_queued() -> None:
    while _process_one():
        pass


def _process_one() -> bool:
    """Pick up the oldest queued run, execute it. Returns True if one was processed."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT r.id, r.dataset_id, r.date_start, r.date_end,
                       d.slug AS dataset_slug,
                       d.scan_window_hours AS dataset_scan_window_hours,
                       pv.params_json
                  FROM runs r
                  JOIN param_versions pv ON r.param_version_id = pv.id
                  JOIN datasets d ON r.dataset_id = d.id
                 WHERE r.status = 'queued'
                 ORDER BY r.created_at ASC
                 LIMIT 1
                """
            )
            row = cur.fetchone()
        if row is None:
            return False
        run_id = row["id"]
        dataset_id = row["dataset_id"]
        dataset_slug = row["dataset_slug"]
        date_start = row["date_start"]
        date_end = row["date_end"]
        scan_window_hours = float(row["dataset_scan_window_hours"])
        params = json.loads(row["params_json"])
        scanner_max_workers_env = os.environ.get("TYCHOS_SCANNER_MAX_WORKERS")
        scanner_max_workers = int(scanner_max_workers_env) if scanner_max_workers_env else None

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE runs SET status='running', started_at=%s WHERE id=%s",
                (_now(), run_id),
            )
        conn.commit()

    try:
        eclipses = load_eclipse_catalog(dataset_id)
        if date_start and date_end:
            eclipses = [e for e in eclipses if date_start <= e["date"] <= date_end]

        # --- unchanged scanner + enrichment block ---
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT julian_day_tt, separation_arcmin, best_jd, "
                    "sun_ra_rad, sun_dec_rad, moon_ra_rad, moon_dec_rad "
                    "FROM jpl_reference WHERE dataset_id=%s",
                    (dataset_id,),
                )
                jpl_rows = cur.fetchall()
        jpl_by_jd = {row["julian_day_tt"]: row for row in jpl_rows}
        jpl_best_lookup = {jd: row["best_jd"] for jd, row in jpl_by_jd.items() if row["best_jd"] is not None}

        if dataset_slug == "solar_eclipse":
            results = scan_solar_eclipses(params, eclipses, half_window_hours=scan_window_hours, jpl_best_jd_by_catalog_jd=jpl_best_lookup, max_workers=scanner_max_workers)
        elif dataset_slug == "lunar_eclipse":
            results = scan_lunar_eclipses(params, eclipses, half_window_hours=scan_window_hours, jpl_best_jd_by_catalog_jd=jpl_best_lookup, max_workers=scanner_max_workers)
        else:
            raise ValueError(f"Unknown dataset slug: {dataset_slug}")

        detected = sum(1 for r in results if r["detected"])
        test_type = "solar" if dataset_slug == "solar_eclipse" else "lunar"

        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT julian_day_tt, expected_separation_arcmin FROM predicted_reference WHERE test_type=%s", (test_type,))
                pred_rows = cur.fetchall()
        pred_by_jd = {row["julian_day_tt"]: row for row in pred_rows}

        RAD_TO_ARCMIN = (180.0 / math.pi) * 60.0

        for r in results:
            pred = pred_by_jd.get(r["julian_day_tt"])
            jpl = jpl_by_jd.get(r["julian_day_tt"])
            r["tychos_error_arcmin"] = round(abs(r["min_separation_arcmin"] - pred["expected_separation_arcmin"]), 4) if pred and r["min_separation_arcmin"] is not None else None
            r["jpl_error_arcmin"] = round(abs(jpl["separation_arcmin"] - pred["expected_separation_arcmin"]), 4) if pred and jpl else None
            r["jpl_timing_offset_min"] = round((jpl["best_jd"] - r["julian_day_tt"]) * 1440.0, 1) if jpl and jpl["best_jd"] is not None else None
            r["moon_error_arcmin"] = None
            if jpl and r.get("tychos_sun_ra_at_jpl_rad") is not None and jpl["sun_ra_rad"] is not None and jpl["moon_ra_rad"] is not None:
                cos_s = math.cos(jpl["sun_dec_rad"])
                cos_m = math.cos(jpl["moon_dec_rad"])
                r["sun_delta_ra_arcmin"] = round((r["tychos_sun_ra_at_jpl_rad"] - jpl["sun_ra_rad"]) * cos_s * RAD_TO_ARCMIN, 4)
                r["sun_delta_dec_arcmin"] = round((r["tychos_sun_dec_at_jpl_rad"] - jpl["sun_dec_rad"]) * RAD_TO_ARCMIN, 4)
                r["moon_delta_ra_arcmin"] = round((r["tychos_moon_ra_at_jpl_rad"] - jpl["moon_ra_rad"]) * cos_m * RAD_TO_ARCMIN, 4)
                r["moon_delta_dec_arcmin"] = round((r["tychos_moon_dec_at_jpl_rad"] - jpl["moon_dec_rad"]) * RAD_TO_ARCMIN, 4)
            else:
                r["sun_delta_ra_arcmin"] = r["sun_delta_dec_arcmin"] = r["moon_delta_ra_arcmin"] = r["moon_delta_dec_arcmin"] = None

        insert_sql = """
            INSERT INTO eclipse_results (
                run_id, julian_day_tt, date, catalog_type, magnitude,
                detected, threshold_arcmin, min_separation_arcmin,
                timing_offset_min, best_jd,
                sun_ra_rad, sun_dec_rad, moon_ra_rad, moon_dec_rad,
                moon_error_arcmin, moon_ra_vel, moon_dec_vel,
                tychos_error_arcmin, jpl_error_arcmin, jpl_timing_offset_min,
                sun_delta_ra_arcmin, sun_delta_dec_arcmin,
                moon_delta_ra_arcmin, moon_delta_dec_arcmin,
                tychos_sun_ra_at_jpl_rad, tychos_sun_dec_at_jpl_rad,
                tychos_moon_ra_at_jpl_rad, tychos_moon_dec_at_jpl_rad
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """
        rows = [
            (
                run_id, r["julian_day_tt"], r["date"], r["catalog_type"], r["magnitude"],
                r["detected"], r["threshold_arcmin"], r["min_separation_arcmin"],
                r["timing_offset_min"], r["best_jd"],
                r["sun_ra_rad"], r["sun_dec_rad"], r["moon_ra_rad"], r["moon_dec_rad"],
                r["moon_error_arcmin"], r.get("moon_ra_vel"), r.get("moon_dec_vel"),
                r["tychos_error_arcmin"], r["jpl_error_arcmin"], r["jpl_timing_offset_min"],
                r["sun_delta_ra_arcmin"], r["sun_delta_dec_arcmin"],
                r["moon_delta_ra_arcmin"], r["moon_delta_dec_arcmin"],
                r.get("tychos_sun_ra_at_jpl_rad"), r.get("tychos_sun_dec_at_jpl_rad"),
                r.get("tychos_moon_ra_at_jpl_rad"), r.get("tychos_moon_dec_at_jpl_rad"),
            )
            for r in results
        ]
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.executemany(insert_sql, rows)
            conn.commit()

        sun_mags, moon_mags, timing_abs = [], [], []
        for r in results:
            if r.get("sun_delta_ra_arcmin") is not None and r.get("sun_delta_dec_arcmin") is not None:
                sun_mags.append(math.sqrt(r["sun_delta_ra_arcmin"]**2 + r["sun_delta_dec_arcmin"]**2))
            if r.get("moon_delta_ra_arcmin") is not None and r.get("moon_delta_dec_arcmin") is not None:
                moon_mags.append(math.sqrt(r["moon_delta_ra_arcmin"]**2 + r["moon_delta_dec_arcmin"]**2))
            if r.get("timing_offset_min") is not None:
                timing_abs.append(abs(r["timing_offset_min"]))

        mean_sun_diff = round(sum(sun_mags)/len(sun_mags), 4) if sun_mags else None
        mean_moon_diff = round(sum(moon_mags)/len(moon_mags), 4) if moon_mags else None
        mean_timing_offset = round(sum(timing_abs)/len(timing_abs), 4) if timing_abs else None

        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE runs SET status='done', completed_at=%s, total_eclipses=%s, detected=%s, "
                    "mean_sun_diff=%s, mean_moon_diff=%s, mean_timing_offset=%s WHERE id=%s",
                    (_now(), len(results), detected, mean_sun_diff, mean_moon_diff, mean_timing_offset, run_id),
                )
            conn.commit()

        print(f"[worker] Run {run_id} complete: {detected}/{len(results)}")
        return True

    except Exception as exc:
        error_text = traceback.format_exc()[:2000]
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE runs SET status='failed', error=%s, completed_at=%s WHERE id=%s",
                    (error_text, _now(), run_id),
                )
            conn.commit()
        print(f"[worker] Run {run_id} failed: {exc}")
        return True


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    from server.db import init_db
    init_db()
    print("[worker] Starting standalone worker process")
    _worker_loop()
```

- [ ] **Step 4: Run test — expect PASS**

Run: `TYCHOS_ADMIN_USER=admin@t.local TYCHOS_ADMIN_PASSWORD=pw DATABASE_URL=postgres://tychos:tychos@localhost:5432/tychos_test PYTHONPATH=tychos_skyfield:tests:. pytest tests/test_worker_notify.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add server/worker.py tests/test_worker_notify.py
git commit -m "feat(worker): port to postgres with LISTEN/NOTIFY"
```

---

## Task 10: View API endpoint

**Files:**
- Create: `server/api/views_routes.py`
- Modify: `server/app.py` (register router)
- Create: `tests/api/test_views.py`

- [ ] **Step 1: Write the failing test `tests/api/test_views.py`**

```python
import json
import pytest
import httpx
from server.db import init_db, get_db
from server.app import app


@pytest.fixture(autouse=True)
def _init():
    init_db()


async def _insert_result(run_id: int, **kwargs):
    with get_db() as conn:
        cols = ", ".join(kwargs.keys())
        ph = ", ".join(["%s"] * len(kwargs))
        with conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO eclipse_results (run_id, julian_day_tt, date, catalog_type, magnitude, detected, threshold_arcmin, {cols}) "
                f"VALUES (%s, 2450000.0, '2000-01-01T00:00:00', 'total', 1.0, true, 0.5, {ph})",
                (run_id, *kwargs.values()),
            )
        conn.commit()


@pytest.mark.asyncio
async def test_view_returns_objective_and_detail(seed_run):
    run_id = seed_run  # fixture creates a run with 2 known result rows
    async with httpx.AsyncClient(app=app, base_url="http://test") as c:
        r = await c.get(f"/api/results/{run_id}/view/v_solar_position")
    assert r.status_code == 200
    data = r.json()
    assert "objective" in data
    assert "detail" in data
    assert data["n_scored"] == 2
    # detail sorted worst-first
    assert data["detail"][0]["error"] >= data["detail"][1]["error"]


@pytest.mark.asyncio
async def test_view_unknown_name_returns_404():
    async with httpx.AsyncClient(app=app, base_url="http://test") as c:
        r = await c.get("/api/results/1/view/v_nonexistent")
    assert r.status_code == 404
```

Add a `seed_run` fixture in `tests/api/conftest.py`:
```python
import pytest
import pytest_asyncio
from server.db import init_db, get_db


@pytest.fixture
def seed_run():
    init_db()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM param_versions ORDER BY id LIMIT 1")
            pv_id = cur.fetchone()[0]
            cur.execute("SELECT id FROM datasets ORDER BY id LIMIT 1")
            ds_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO runs (param_version_id, dataset_id, status) VALUES (%s,%s,'done') RETURNING id",
                (pv_id, ds_id),
            )
            run_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO eclipse_results (run_id, julian_day_tt, date, catalog_type, magnitude, detected, threshold_arcmin, sun_delta_ra_arcmin, sun_delta_dec_arcmin, moon_delta_ra_arcmin, moon_delta_dec_arcmin) "
                "VALUES (%s, 2450000.0, '2000-01-01', 'total', 1.0, true, 0.5, 3.0, 4.0, 6.0, 8.0)",
                (run_id,),
            )
            cur.execute(
                "INSERT INTO eclipse_results (run_id, julian_day_tt, date, catalog_type, magnitude, detected, threshold_arcmin, sun_delta_ra_arcmin, sun_delta_dec_arcmin, moon_delta_ra_arcmin, moon_delta_dec_arcmin) "
                "VALUES (%s, 2450001.0, '2001-01-01', 'total', 1.0, true, 0.5, 1.0, 0.0, 3.0, 4.0)",
                (run_id,),
            )
        conn.commit()
    return run_id
```

- [ ] **Step 2: Run test — expect FAIL (router not implemented)**

Run: `TYCHOS_ADMIN_USER=admin@t.local TYCHOS_ADMIN_PASSWORD=pw DATABASE_URL=postgres://tychos:tychos@localhost:5432/tychos_test PYTHONPATH=tychos_skyfield:tests:. pytest tests/api/test_views.py -v`

- [ ] **Step 3: Implement `server/api/views_routes.py`**

```python
"""GET /api/results/{run_id}/view/{view_name} — per-objective result lens."""
from fastapi import APIRouter, HTTPException
from server.db import get_async_db

router = APIRouter(prefix="/api/results")

_ALLOWED_VIEWS = {"v_solar_position", "v_moon_position", "v_combined_position"}


@router.get("/{run_id}/view/{view_name}")
async def get_view(run_id: int, view_name: str):
    if view_name not in _ALLOWED_VIEWS:
        raise HTTPException(status_code=404, detail=f"Unknown view: {view_name}")

    async with get_async_db() as conn:
        # Optional date filter: look up the research job's range for this run (if any).
        job_range = await conn.fetchrow(
            """
            SELECT date_start, date_end FROM runs WHERE id = $1
            """,
            run_id,
        )
        date_start = job_range["date_start"] if job_range else None
        date_end = job_range["date_end"] if job_range else None

        filters = ["run_id = $1"]
        args = [run_id]
        if date_start:
            filters.append(f"date >= ${len(args)+1}")
            args.append(date_start)
        if date_end:
            filters.append(f"date <= ${len(args)+1}")
            args.append(date_end)
        where = " AND ".join(filters)

        obj_row = await conn.fetchrow(
            f"SELECT AVG(error) AS objective, COUNT(*) AS n FROM {view_name} WHERE {where}",
            *args,
        )
        detail_rows = await conn.fetch(
            f"SELECT * FROM {view_name} WHERE {where} ORDER BY error DESC",
            *args,
        )

    return {
        "objective": float(obj_row["objective"]) if obj_row["objective"] is not None else None,
        "n_scored": int(obj_row["n"]),
        "detail": [dict(r) for r in detail_rows],
    }
```

- [ ] **Step 4: Register router in `server/app.py`**

Add after existing `include_router` calls:
```python
from server.api.views_routes import router as views_router  # noqa: E402
app.include_router(views_router)
```

- [ ] **Step 5: Run test — expect PASS**

Run: `TYCHOS_ADMIN_USER=admin@t.local TYCHOS_ADMIN_PASSWORD=pw DATABASE_URL=postgres://tychos:tychos@localhost:5432/tychos_test PYTHONPATH=tychos_skyfield:tests:. pytest tests/api/test_views.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add server/api/views_routes.py server/app.py tests/api/
git commit -m "feat(api): add view-based result endpoint"
```

---

## Task 11: Research CRUD endpoints

**Files:**
- Create: `server/api/research_routes.py`
- Create: `server/research/instructions.py`
- Create: `server/research/templates/instructions.md.tmpl`
- Modify: `server/app.py` (register `research_router`)
- Create: `tests/api/test_research_crud.py`

- [ ] **Step 1: Write failing test `tests/api/test_research_crud.py`**

```python
import pytest
import httpx
from server.db import init_db
from server.app import app


@pytest.fixture(autouse=True)
def _init():
    init_db()


async def _login(c):
    r = await c.post("/api/auth/login", json={"email": "admin@t.local", "password": "pw"})
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_create_and_get_research_job():
    async with httpx.AsyncClient(app=app, base_url="http://test") as c:
        await _login(c)
        r = await c.post("/api/research", json={
            "name": "solar-sim-test",
            "param_set_id": 1,
            "dataset_id": 1,
            "view_name": "v_solar_position",
            "allowlist": ["sun.*"],
            "date_start": "1900-01-01",
            "date_end": "2050-12-31",
        })
        assert r.status_code == 201
        job = r.json()
        assert job["id"] > 0
        assert job["status"] == "active"
        assert job["instructions"]  # populated by template

        r2 = await c.get(f"/api/research/{job['id']}")
        assert r2.status_code == 200
        assert r2.json()["name"] == "solar-sim-test"


@pytest.mark.asyncio
async def test_list_research_jobs():
    async with httpx.AsyncClient(app=app, base_url="http://test") as c:
        r = await c.get("/api/research")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_patch_research_job_status():
    async with httpx.AsyncClient(app=app, base_url="http://test") as c:
        await _login(c)
        created = (await c.post("/api/research", json={
            "name": "paused-job", "param_set_id": 1, "dataset_id": 1,
            "view_name": "v_solar_position", "allowlist": ["sun.*"],
        })).json()
        r = await c.patch(f"/api/research/{created['id']}", json={"status": "paused"})
        assert r.status_code == 200
        assert r.json()["status"] == "paused"


@pytest.mark.asyncio
async def test_view_name_validated_on_create():
    async with httpx.AsyncClient(app=app, base_url="http://test") as c:
        await _login(c)
        r = await c.post("/api/research", json={
            "name": "bad", "param_set_id": 1, "dataset_id": 1,
            "view_name": "v_bogus", "allowlist": ["sun.*"],
        })
        assert r.status_code == 422
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `pytest tests/api/test_research_crud.py -v` — router missing.

- [ ] **Step 3: Write `server/research/templates/instructions.md.tmpl`**

Copy the existing `program.md.tmpl` but change its frontmatter fields from (`job`, `dataset`, `base_param_version`, `allowlist`) to the new metadata block and rewrite the loop section to reference API endpoints instead of CLI commands:

```markdown
---
job: {job_name}
dataset: {dataset_slug}
view: {view_name}
date_range: {date_range}
allowlist:
{allowlist_yaml}
---

# Research job: {job_name}

## Goal
Lower `objective = AVG(error)` from SQL view `{view_name}` on dataset `{dataset_slug}`
{date_range_sentence}
by editing allowlisted parameters of param_set {param_set_id}. Lower is better.

## The loop (API-driven)
1. `GET /api/research/{job_id}` — read this config and the latest checkpoint version_id.
2. `GET /api/params/<param_set_id>/versions/<latest_checkpoint_version_id>` — read current params.
3. Edit allowlisted keys only, then `POST /api/research/{job_id}/version` with `{{ "params_json": "..." }}` — returns `version_id`, `run_id`.
4. Poll `GET /api/runs/<run_id>` until `status=="done"`.
5. `GET /api/results/<run_id>/view/{view_name}` — returns `objective`, `n_scored`, per-eclipse `detail` (worst-first).
6. `POST /api/research/{job_id}/iterations` with the `version_id`, `run_id`, `kind="iterate"`, `objective`, `aux_stats` — logs the iteration.
7. If improved: `POST /api/research/{job_id}/checkpoint/{{{{version_id}}}}` marks the winner.
8. If worse: `POST /api/research/{job_id}/restore/<last_checkpoint_version_id>` creates a new version from the checkpoint params.

## Joint search (server-side Nelder-Mead)
`POST /api/research/{job_id}/search` with `param_keys`, `budget`, `scale`.
Uses the in-process scanner; winner gets a new version + queued run + checkpoint.

## Background
{background}
```

- [ ] **Step 4: Write `server/research/instructions.py`**

```python
"""Render research-job instructions from the template."""
from pathlib import Path

_TEMPLATE_PATH = Path(__file__).parent / "templates" / "instructions.md.tmpl"
_BACKGROUND_PATH = Path(__file__).parent / "templates" / "background.md"


def render_instructions(
    *,
    job_id: int,
    job_name: str,
    dataset_slug: str,
    view_name: str,
    allowlist: list[str],
    param_set_id: int,
    date_start: str | None,
    date_end: str | None,
) -> str:
    if date_start and date_end:
        date_range = f"{date_start} to {date_end}"
        date_range_sentence = f"(restricted to eclipses in {date_range})"
    else:
        date_range = "full catalog"
        date_range_sentence = "(full catalog)"
    allowlist_yaml = "\n".join(f"  - {a}" for a in allowlist)
    background = _BACKGROUND_PATH.read_text() if _BACKGROUND_PATH.exists() else ""
    return _TEMPLATE_PATH.read_text().format(
        job_id=job_id,
        job_name=job_name,
        dataset_slug=dataset_slug,
        view_name=view_name,
        date_range=date_range,
        date_range_sentence=date_range_sentence,
        allowlist_yaml=allowlist_yaml,
        param_set_id=param_set_id,
        background=background,
    )
```

Create `server/research/templates/background.md` by copying the Parts A/B/C/D section from the existing `program.md.tmpl` (lines 54–141).

- [ ] **Step 5: Implement `server/api/research_routes.py` (CRUD only — iterations/version/search come in later tasks)**

```python
"""Research job endpoints."""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from server.auth import require_user
from server.db import get_async_db
from server.research.instructions import render_instructions

router = APIRouter(prefix="/api/research")

_ALLOWED_VIEWS = {"v_solar_position", "v_moon_position", "v_combined_position"}
_ALLOWED_STATUSES = {"active", "paused", "completed"}


class CreateJobBody(BaseModel):
    name: str
    param_set_id: int
    dataset_id: int
    view_name: str
    allowlist: list[str]
    date_start: str | None = None
    date_end: str | None = None


class UpdateJobBody(BaseModel):
    status: str | None = None


@router.get("")
async def list_research_jobs():
    async with get_async_db() as conn:
        rows = await conn.fetch(
            "SELECT * FROM research_jobs ORDER BY created_at DESC"
        )
    return [dict(r) for r in rows]


@router.post("", status_code=201)
async def create_research_job(body: CreateJobBody, request: Request):
    await require_user(request)
    if body.view_name not in _ALLOWED_VIEWS:
        raise HTTPException(status_code=422, detail=f"Unknown view_name: {body.view_name}")
    if not body.allowlist:
        raise HTTPException(status_code=422, detail="allowlist must be non-empty")

    async with get_async_db() as conn:
        ps = await conn.fetchrow("SELECT id, name FROM param_sets WHERE id=$1", body.param_set_id)
        if not ps:
            raise HTTPException(status_code=404, detail="param_set_id not found")
        ds = await conn.fetchrow("SELECT id, slug FROM datasets WHERE id=$1", body.dataset_id)
        if not ds:
            raise HTTPException(status_code=404, detail="dataset_id not found")

        job_id = await conn.fetchval(
            "INSERT INTO research_jobs (name, param_set_id, dataset_id, view_name, allowlist, date_start, date_end) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING id",
            body.name, body.param_set_id, body.dataset_id, body.view_name,
            body.allowlist, body.date_start, body.date_end,
        )

        instructions = render_instructions(
            job_id=job_id,
            job_name=body.name,
            dataset_slug=ds["slug"],
            view_name=body.view_name,
            allowlist=body.allowlist,
            param_set_id=body.param_set_id,
            date_start=body.date_start,
            date_end=body.date_end,
        )
        await conn.execute(
            "UPDATE research_jobs SET instructions=$1 WHERE id=$2",
            instructions, job_id,
        )

        row = await conn.fetchrow("SELECT * FROM research_jobs WHERE id=$1", job_id)
    return dict(row)


@router.get("/{job_id}")
async def get_research_job(job_id: int):
    async with get_async_db() as conn:
        row = await conn.fetchrow("SELECT * FROM research_jobs WHERE id=$1", job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Research job not found")
    return dict(row)


@router.patch("/{job_id}")
async def update_research_job(job_id: int, body: UpdateJobBody, request: Request):
    await require_user(request)
    if body.status is not None and body.status not in _ALLOWED_STATUSES:
        raise HTTPException(status_code=422, detail=f"status must be one of {_ALLOWED_STATUSES}")

    async with get_async_db() as conn:
        existing = await conn.fetchrow("SELECT id FROM research_jobs WHERE id=$1", job_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Research job not found")
        if body.status is not None:
            await conn.execute(
                "UPDATE research_jobs SET status=$1, updated_at=to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS') WHERE id=$2",
                body.status, job_id,
            )
        row = await conn.fetchrow("SELECT * FROM research_jobs WHERE id=$1", job_id)
    return dict(row)
```

- [ ] **Step 6: Register router in `server/app.py`**

Add:
```python
from server.api.research_routes import router as research_router  # noqa: E402
app.include_router(research_router)
```

- [ ] **Step 7: Run test — expect PASS**

Run: `pytest tests/api/test_research_crud.py -v`

- [ ] **Step 8: Commit**

```bash
git add server/api/research_routes.py server/research/instructions.py server/research/templates/ server/app.py tests/api/test_research_crud.py
git commit -m "feat(research): add research job CRUD endpoints"
```

---

## Task 12: Keep allowlist validator; add version endpoint with enforcement

**Files:**
- Modify: `server/research/allowlist.py` (strip imports the deleted files bring)
- Modify: `server/api/research_routes.py` (add `POST /api/research/{job_id}/version`)
- Create: `tests/api/test_research_version.py`

- [ ] **Step 1: Trim `server/research/allowlist.py`**

Keep the file exactly as-is except remove the `from server.research.sandbox import ...` if present (it isn't, so this is a no-op — just re-read the file to confirm).

- [ ] **Step 2: Write failing test `tests/api/test_research_version.py`**

```python
import json
import pytest
import httpx
from server.db import init_db, get_db
from server.app import app


@pytest.fixture(autouse=True)
def _init():
    init_db()


async def _login(c):
    await c.post("/api/auth/login", json={"email": "admin@t.local", "password": "pw"})


async def _create_job(c, allowlist):
    await _login(c)
    r = await c.post("/api/research", json={
        "name": "version-test", "param_set_id": 1, "dataset_id": 1,
        "view_name": "v_solar_position", "allowlist": allowlist,
    })
    return r.json()


@pytest.mark.asyncio
async def test_version_endpoint_creates_version_and_run():
    async with httpx.AsyncClient(app=app, base_url="http://test") as c:
        job = await _create_job(c, ["sun.*"])
        # Read latest params
        ps = (await c.get(f"/api/params/{job['param_set_id']}")).json()
        latest = ps["versions"][0]
        base_params = json.loads(
            (await c.get(f"/api/params/{job['param_set_id']}/versions/{latest['id']}")).json()["params_json"]
        )
        # Mutate an allowlisted key
        base_params["sun"]["start_pos"] = base_params["sun"]["start_pos"] + 0.1
        r = await c.post(
            f"/api/research/{job['id']}/version",
            json={"params_json": json.dumps(base_params)},
        )
        assert r.status_code == 201
        body = r.json()
        assert body["version_id"] > 0
        assert body["run_id"] > 0


@pytest.mark.asyncio
async def test_version_endpoint_rejects_non_allowlisted_change():
    async with httpx.AsyncClient(app=app, base_url="http://test") as c:
        job = await _create_job(c, ["sun.*"])
        ps = (await c.get(f"/api/params/{job['param_set_id']}")).json()
        latest_id = ps["versions"][0]["id"]
        base_params = json.loads(
            (await c.get(f"/api/params/{job['param_set_id']}/versions/{latest_id}")).json()["params_json"]
        )
        base_params["moon"]["start_pos"] = base_params["moon"]["start_pos"] + 0.1
        r = await c.post(
            f"/api/research/{job['id']}/version",
            json={"params_json": json.dumps(base_params)},
        )
        assert r.status_code == 400
        assert "allowlist" in r.json()["detail"].lower()
```

- [ ] **Step 3: Run test — expect FAIL**

- [ ] **Step 4: Add version endpoint to `server/api/research_routes.py`**

```python
import hashlib
import json as _json
from server.research.allowlist import check_diff_against_allowlist, AllowlistViolation


class CreateVersionBody(BaseModel):
    params_json: str
    notes: str | None = None


@router.post("/{job_id}/version", status_code=201)
async def create_research_version(job_id: int, body: CreateVersionBody, request: Request):
    await require_user(request)
    async with get_async_db() as conn:
        job = await conn.fetchrow("SELECT * FROM research_jobs WHERE id=$1", job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Research job not found")

        # Baseline for diff: latest checkpoint on this param_set, else v1.
        base_row = await conn.fetchrow(
            "SELECT params_json FROM param_versions "
            "WHERE param_set_id=$1 AND is_checkpoint=TRUE "
            "ORDER BY version_number DESC LIMIT 1",
            job["param_set_id"],
        )
        if base_row is None:
            base_row = await conn.fetchrow(
                "SELECT params_json FROM param_versions WHERE param_set_id=$1 ORDER BY version_number ASC LIMIT 1",
                job["param_set_id"],
            )
        baseline = _json.loads(base_row["params_json"])

        try:
            new_params = _json.loads(body.params_json)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"params_json invalid: {exc}")

        try:
            check_diff_against_allowlist(
                new_params, baseline,
                allowlist_globs=list(job["allowlist"]),
                known_bodies=list(baseline.keys()),
            )
        except AllowlistViolation as exc:
            raise HTTPException(status_code=400, detail=f"allowlist violation: {exc}")

        # New version
        latest_num = await conn.fetchval(
            "SELECT COALESCE(MAX(version_number),0) FROM param_versions WHERE param_set_id=$1",
            job["param_set_id"],
        )
        md5 = hashlib.md5(_json.dumps(new_params, sort_keys=True).encode()).hexdigest()
        version_id = await conn.fetchval(
            "INSERT INTO param_versions (param_set_id, version_number, params_md5, params_json, notes) "
            "VALUES ($1,$2,$3,$4,$5) RETURNING id",
            job["param_set_id"], latest_num + 1, md5, body.params_json, body.notes,
        )
        run_id = await conn.fetchval(
            "INSERT INTO runs (param_version_id, dataset_id, status, date_start, date_end) "
            "VALUES ($1,$2,'queued',$3,$4) RETURNING id",
            version_id, job["dataset_id"], job["date_start"], job["date_end"],
        )

    return {"version_id": version_id, "run_id": run_id}
```

- [ ] **Step 5: Run test — expect PASS**

- [ ] **Step 6: Commit**

```bash
git add server/api/research_routes.py tests/api/test_research_version.py
git commit -m "feat(research): version endpoint with allowlist enforcement"
```

---

## Task 13: Iterations, checkpoint, restore endpoints

**Files:**
- Modify: `server/api/research_routes.py`
- Create: `tests/api/test_research_iterations.py`

- [ ] **Step 1: Write failing tests**

```python
import json
import pytest
import httpx
from server.db import init_db
from server.app import app


@pytest.fixture(autouse=True)
def _init():
    init_db()


@pytest.mark.asyncio
async def test_log_and_list_iterations():
    async with httpx.AsyncClient(app=app, base_url="http://test") as c:
        await c.post("/api/auth/login", json={"email": "admin@t.local", "password": "pw"})
        job = (await c.post("/api/research", json={
            "name": "iter-test", "param_set_id": 1, "dataset_id": 1,
            "view_name": "v_solar_position", "allowlist": ["sun.*"],
        })).json()
        # Fetch an existing version to reference
        ps = (await c.get(f"/api/params/{job['param_set_id']}")).json()
        version_id = ps["versions"][0]["id"]

        r = await c.post(f"/api/research/{job['id']}/iterations", json={
            "param_version_id": version_id,
            "run_id": None,
            "kind": "iterate",
            "objective": 12.34,
            "aux_stats": {"mean_sun_error_arcmin": 12.3, "n_total": 450},
        })
        assert r.status_code == 201
        it = r.json()
        assert it["objective"] == 12.34

        r2 = await c.get(f"/api/research/{job['id']}/iterations")
        assert r2.status_code == 200
        assert any(i["id"] == it["id"] for i in r2.json())


@pytest.mark.asyncio
async def test_checkpoint_and_restore():
    async with httpx.AsyncClient(app=app, base_url="http://test") as c:
        await c.post("/api/auth/login", json={"email": "admin@t.local", "password": "pw"})
        job = (await c.post("/api/research", json={
            "name": "ckpt-test", "param_set_id": 1, "dataset_id": 1,
            "view_name": "v_solar_position", "allowlist": ["sun.*"],
        })).json()
        ps = (await c.get(f"/api/params/{job['param_set_id']}")).json()
        version_id = ps["versions"][0]["id"]

        r = await c.post(f"/api/research/{job['id']}/checkpoint/{version_id}")
        assert r.status_code == 200
        assert r.json()["is_checkpoint"] is True

        r2 = await c.post(f"/api/research/{job['id']}/restore/{version_id}")
        assert r2.status_code == 201
        restored = r2.json()
        assert restored["version_id"] > version_id
        assert restored["run_id"] > 0
```

- [ ] **Step 2: Run tests — expect FAIL**

- [ ] **Step 3: Add endpoints to `server/api/research_routes.py`**

```python
class LogIterationBody(BaseModel):
    param_version_id: int
    run_id: int | None = None
    kind: str
    objective: float | None = None
    aux_stats: dict | None = None


@router.get("/{job_id}/iterations")
async def list_iterations(job_id: int):
    async with get_async_db() as conn:
        rows = await conn.fetch(
            "SELECT * FROM research_iterations WHERE research_job_id=$1 ORDER BY created_at ASC",
            job_id,
        )
    return [dict(r) for r in rows]


@router.post("/{job_id}/iterations", status_code=201)
async def log_iteration(job_id: int, body: LogIterationBody, request: Request):
    await require_user(request)
    if body.kind not in ("iterate", "search_eval", "search_winner"):
        raise HTTPException(status_code=422, detail="Invalid kind")
    async with get_async_db() as conn:
        row = await conn.fetchrow(
            "INSERT INTO research_iterations (research_job_id, param_version_id, run_id, kind, objective, aux_stats) "
            "VALUES ($1,$2,$3,$4,$5,$6) RETURNING *",
            job_id, body.param_version_id, body.run_id, body.kind, body.objective,
            _json.dumps(body.aux_stats) if body.aux_stats else None,
        )
    return dict(row)


@router.post("/{job_id}/checkpoint/{version_id}")
async def mark_checkpoint(job_id: int, version_id: int, request: Request):
    await require_user(request)
    async with get_async_db() as conn:
        job = await conn.fetchrow("SELECT param_set_id FROM research_jobs WHERE id=$1", job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Research job not found")
        v = await conn.fetchrow(
            "SELECT id FROM param_versions WHERE id=$1 AND param_set_id=$2",
            version_id, job["param_set_id"],
        )
        if not v:
            raise HTTPException(status_code=404, detail="Version not found on this job's param set")
        row = await conn.fetchrow(
            "UPDATE param_versions SET is_checkpoint=TRUE WHERE id=$1 RETURNING *",
            version_id,
        )
    return dict(row)


@router.post("/{job_id}/restore/{version_id}", status_code=201)
async def restore_from_version(job_id: int, version_id: int, request: Request):
    await require_user(request)
    async with get_async_db() as conn:
        job = await conn.fetchrow("SELECT * FROM research_jobs WHERE id=$1", job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Research job not found")
        src = await conn.fetchrow(
            "SELECT params_json FROM param_versions WHERE id=$1 AND param_set_id=$2",
            version_id, job["param_set_id"],
        )
        if not src:
            raise HTTPException(status_code=404, detail="Source version not found on this job's param set")
        params_json = src["params_json"]
        md5 = hashlib.md5(_json.dumps(_json.loads(params_json), sort_keys=True).encode()).hexdigest()
        latest_num = await conn.fetchval(
            "SELECT COALESCE(MAX(version_number),0) FROM param_versions WHERE param_set_id=$1",
            job["param_set_id"],
        )
        new_version_id = await conn.fetchval(
            "INSERT INTO param_versions (param_set_id, version_number, parent_version_id, params_md5, params_json, notes) "
            "VALUES ($1,$2,$3,$4,$5,$6) RETURNING id",
            job["param_set_id"], latest_num + 1, version_id, md5, params_json,
            f"restored from version {version_id}",
        )
        run_id = await conn.fetchval(
            "INSERT INTO runs (param_version_id, dataset_id, status, date_start, date_end) "
            "VALUES ($1,$2,'queued',$3,$4) RETURNING id",
            new_version_id, job["dataset_id"], job["date_start"], job["date_end"],
        )
    return {"version_id": new_version_id, "run_id": run_id}
```

- [ ] **Step 4: Run tests — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add server/api/research_routes.py tests/api/test_research_iterations.py
git commit -m "feat(research): iterations, checkpoint, restore endpoints"
```

---

## Task 14: Server-side Nelder-Mead search endpoint

**Files:**
- Create: `server/research/search_engine.py`
- Modify: `server/api/research_routes.py`
- Create: `tests/api/test_research_search.py`

- [ ] **Step 1: Move `run_search` logic into `server/research/search_engine.py`**

Copy the existing `server/research/search.py` file contents verbatim into `server/research/search_engine.py`. This module is pure optimizer; no DB dependencies. The old `server/research/search.py` will be deleted in the cleanup task.

- [ ] **Step 2: Write failing test `tests/api/test_research_search.py`**

```python
import json
import pytest
import httpx
from server.db import init_db
from server.app import app


@pytest.fixture(autouse=True)
def _init():
    init_db()


@pytest.mark.asyncio
async def test_search_endpoint_runs_and_returns_winner():
    async with httpx.AsyncClient(app=app, base_url="http://test", timeout=120.0) as c:
        await c.post("/api/auth/login", json={"email": "admin@t.local", "password": "pw"})
        job = (await c.post("/api/research", json={
            "name": "search-test", "param_set_id": 1, "dataset_id": 1,
            "view_name": "v_solar_position", "allowlist": ["sun.*"],
            "date_start": "1950-01-01", "date_end": "1960-12-31",
        })).json()

        r = await c.post(f"/api/research/{job['id']}/search", json={
            "param_keys": ["sun.start_pos"],
            "budget": 6,
            "scale": 0.01,
        })
        assert r.status_code == 200
        out = r.json()
        assert "starting_objective" in out
        assert "best_objective" in out
        assert "n_evals" in out
        assert out["winner_version_id"] is None or out["winner_version_id"] > 0
```

- [ ] **Step 3: Run test — expect FAIL**

- [ ] **Step 4: Add search endpoint to `server/api/research_routes.py`**

```python
class SearchBody(BaseModel):
    param_keys: list[str]
    budget: int = 60
    scale: float = 0.01


@router.post("/{job_id}/search")
async def run_research_search(job_id: int, body: SearchBody, request: Request):
    await require_user(request)
    from server.research.search_engine import run_search
    from server.research.allowlist import expand_globs
    from server.services.scanner import scan_solar_eclipses, scan_lunar_eclipses
    import math, copy

    async with get_async_db() as conn:
        job = await conn.fetchrow("SELECT * FROM research_jobs WHERE id=$1", job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Research job not found")
        # Starting params = latest checkpoint or v1
        row = await conn.fetchrow(
            "SELECT id, params_json FROM param_versions WHERE param_set_id=$1 AND is_checkpoint=TRUE ORDER BY version_number DESC LIMIT 1",
            job["param_set_id"],
        )
        if row is None:
            row = await conn.fetchrow(
                "SELECT id, params_json FROM param_versions WHERE param_set_id=$1 ORDER BY version_number ASC LIMIT 1",
                job["param_set_id"],
            )
        starting = _json.loads(row["params_json"])

        allowed = expand_globs(list(job["allowlist"]), list(starting.keys()))
        forbidden = [k for k in body.param_keys if k not in allowed]
        if forbidden:
            raise HTTPException(status_code=400, detail=f"param_keys not in allowlist: {forbidden}")

        ds = await conn.fetchrow("SELECT slug, scan_window_hours FROM datasets WHERE id=$1", job["dataset_id"])
        jpl_rows = await conn.fetch(
            "SELECT julian_day_tt, best_jd, sun_ra_rad, sun_dec_rad, moon_ra_rad, moon_dec_rad "
            "FROM jpl_reference WHERE dataset_id=$1",
            job["dataset_id"],
        )
        cat_filters = ["dataset_id=$1"]
        cat_args = [job["dataset_id"]]
        if job["date_start"]:
            cat_filters.append(f"date >= ${len(cat_args)+1}")
            cat_args.append(job["date_start"])
        if job["date_end"]:
            cat_filters.append(f"date <= ${len(cat_args)+1}")
            cat_args.append(job["date_end"])
        eclipses = [dict(r) for r in await conn.fetch(
            f"SELECT catalog_number, julian_day_tt, date, type, magnitude, gamma, "
            f"pen_mag, um_mag FROM eclipse_catalog WHERE {' AND '.join(cat_filters)} ORDER BY julian_day_tt",
            *cat_args,
        )]

    jpl_by_jd = {r["julian_day_tt"]: r for r in jpl_rows}
    jpl_best_lookup = {jd: r["best_jd"] for jd, r in jpl_by_jd.items() if r["best_jd"] is not None}

    RAD_TO_ARCMIN = (180.0 / math.pi) * 60.0

    def _evaluate(candidate: dict) -> float:
        scan_fn = scan_solar_eclipses if ds["slug"] == "solar_eclipse" else scan_lunar_eclipses
        results = scan_fn(
            candidate, eclipses,
            half_window_hours=float(ds["scan_window_hours"]),
            jpl_best_jd_by_catalog_jd=jpl_best_lookup,
        )
        errs = []
        for r in results:
            jpl = jpl_by_jd.get(r["julian_day_tt"])
            if not jpl or r.get("tychos_sun_ra_at_jpl_rad") is None:
                continue
            cos_s = math.cos(jpl["sun_dec_rad"])
            cos_m = math.cos(jpl["moon_dec_rad"])
            s_dra = (r["tychos_sun_ra_at_jpl_rad"] - jpl["sun_ra_rad"]) * cos_s * RAD_TO_ARCMIN
            s_ddec = (r["tychos_sun_dec_at_jpl_rad"] - jpl["sun_dec_rad"]) * RAD_TO_ARCMIN
            if job["view_name"] == "v_solar_position":
                errs.append(math.sqrt(s_dra*s_dra + s_ddec*s_ddec))
            else:
                m_dra = (r["tychos_moon_ra_at_jpl_rad"] - jpl["moon_ra_rad"]) * cos_m * RAD_TO_ARCMIN
                m_ddec = (r["tychos_moon_dec_at_jpl_rad"] - jpl["moon_dec_rad"]) * RAD_TO_ARCMIN
                if job["view_name"] == "v_moon_position":
                    errs.append(math.sqrt(m_dra*m_dra + m_ddec*m_ddec))
                else:
                    errs.append(math.sqrt(s_dra*s_dra + s_ddec*s_ddec + m_dra*m_dra + m_ddec*m_ddec))
        return float("inf") if not errs else sum(errs)/len(errs)

    search_result = run_search(
        current=starting,
        param_keys=body.param_keys,
        evaluate=_evaluate,
        budget=body.budget,
        scale=body.scale,
    )

    improved = search_result.best_objective < search_result.starting_objective
    winner_version_id = None
    winner_run_id = None

    if improved:
        async with get_async_db() as conn:
            job = await conn.fetchrow("SELECT * FROM research_jobs WHERE id=$1", job_id)
            latest_num = await conn.fetchval(
                "SELECT COALESCE(MAX(version_number),0) FROM param_versions WHERE param_set_id=$1",
                job["param_set_id"],
            )
            params_json = _json.dumps(search_result.best_params, sort_keys=True)
            md5 = hashlib.md5(params_json.encode()).hexdigest()
            winner_version_id = await conn.fetchval(
                "INSERT INTO param_versions (param_set_id, version_number, params_md5, params_json, notes, is_checkpoint) "
                "VALUES ($1,$2,$3,$4,$5,TRUE) RETURNING id",
                job["param_set_id"], latest_num + 1, md5, params_json,
                f"search winner: {body.param_keys} (budget {body.budget})",
            )
            winner_run_id = await conn.fetchval(
                "INSERT INTO runs (param_version_id, dataset_id, status, date_start, date_end) "
                "VALUES ($1,$2,'queued',$3,$4) RETURNING id",
                winner_version_id, job["dataset_id"], job["date_start"], job["date_end"],
            )
            await conn.execute(
                "INSERT INTO research_iterations (research_job_id, param_version_id, run_id, kind, objective) "
                "VALUES ($1,$2,$3,'search_winner',$4)",
                job_id, winner_version_id, winner_run_id, search_result.best_objective,
            )

    return {
        "starting_objective": search_result.starting_objective,
        "best_objective": search_result.best_objective,
        "delta": search_result.best_objective - search_result.starting_objective,
        "improved": improved,
        "n_evals": search_result.n_evals,
        "winner_version_id": winner_version_id,
        "winner_run_id": winner_run_id,
    }
```

- [ ] **Step 5: Run test — expect PASS**

Run: `pytest tests/api/test_research_search.py -v` (may take 30–60s).

- [ ] **Step 6: Commit**

```bash
git add server/research/search_engine.py server/api/research_routes.py tests/api/test_research_search.py
git commit -m "feat(research): server-side Nelder-Mead search endpoint"
```

---

## Task 15: Delete the filesystem research stack

**Files:**
- Delete: `server/research/cli.py`, `__main__.py`, `sandbox.py`, `subset.py`, `program_md.py`, `objective.py`, `search.py`
- Delete: `server/research/templates/program.md.tmpl`
- Delete: `research.sh`
- Delete: `params/research/` (entire directory)
- Delete: `tests/research/test_sandbox.py`, `test_subset.py`, `test_program_md.py`, `test_objective.py`, `test_smoke.py`, `test_allowlist.py`, `conftest.py`
- Keep: `server/research/__init__.py`, `allowlist.py`, `instructions.py`, `search_engine.py`, `templates/instructions.md.tmpl`, `templates/background.md`

- [ ] **Step 1: Delete files**

```bash
rm server/research/cli.py server/research/__main__.py server/research/sandbox.py \
   server/research/subset.py server/research/program_md.py server/research/objective.py \
   server/research/search.py server/research/templates/program.md.tmpl research.sh
rm -rf params/research/
rm tests/research/test_sandbox.py tests/research/test_subset.py \
   tests/research/test_program_md.py tests/research/test_objective.py \
   tests/research/test_smoke.py tests/research/test_allowlist.py tests/research/conftest.py
```

- [ ] **Step 2: Ensure `server/research/__init__.py` has no dangling imports**

Overwrite with a single-line placeholder:
```python
"""Research system: DB-driven, API-first. See docs/specs/."""
```

- [ ] **Step 3: Run full test suite**

Run: `TYCHOS_ADMIN_USER=admin@t.local TYCHOS_ADMIN_PASSWORD=pw DATABASE_URL=postgres://tychos:tychos@localhost:5432/tychos_test PYTHONPATH=tychos_skyfield:tests:. pytest tests/ -v`
Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore(research): remove filesystem-based research system"
```

---

## Task 16: End-to-end research flow test

**Files:**
- Create: `tests/test_research_e2e.py`

Exercises: create job → create version → worker processes → view endpoint returns objective → iteration logged → checkpoint → restore.

- [ ] **Step 1: Write the test**

```python
import json
import time
import pytest
import httpx
import threading

from server.db import init_db, get_db
from server.app import app
from server.worker import start_worker


@pytest.fixture(autouse=True, scope="module")
def _init():
    init_db()
    start_worker()


def _wait_run_done(c, run_id, timeout=120):
    start = time.time()
    while time.time() - start < timeout:
        r = httpx.get(f"http://test/api/runs/{run_id}")  # replaced below
        if r.status_code == 200 and r.json()["status"] in ("done", "failed"):
            return r.json()
        time.sleep(0.5)
    raise TimeoutError(f"Run {run_id} did not finish in {timeout}s")


@pytest.mark.asyncio
async def test_full_research_flow():
    async with httpx.AsyncClient(app=app, base_url="http://test", timeout=180.0) as c:
        await c.post("/api/auth/login", json={"email": "admin@t.local", "password": "pw"})
        job = (await c.post("/api/research", json={
            "name": "e2e", "param_set_id": 1, "dataset_id": 1,
            "view_name": "v_solar_position", "allowlist": ["sun.*"],
            "date_start": "1950-01-01", "date_end": "1951-12-31",
        })).json()

        ps = (await c.get(f"/api/params/{job['param_set_id']}")).json()
        latest_id = ps["versions"][0]["id"]
        base = json.loads((await c.get(f"/api/params/{job['param_set_id']}/versions/{latest_id}")).json()["params_json"])
        base["sun"]["start_pos"] += 0.01

        created = (await c.post(f"/api/research/{job['id']}/version",
                                json={"params_json": json.dumps(base)})).json()
        # Poll for completion
        deadline = time.time() + 180
        while time.time() < deadline:
            run = (await c.get(f"/api/runs/{created['run_id']}")).json()
            if run["status"] in ("done", "failed"):
                break
            import asyncio; await asyncio.sleep(0.5)
        assert run["status"] == "done", f"run failed: {run.get('error')}"

        view = (await c.get(f"/api/results/{created['run_id']}/view/v_solar_position")).json()
        assert view["n_scored"] > 0
        assert view["objective"] is not None

        it = await c.post(f"/api/research/{job['id']}/iterations", json={
            "param_version_id": created["version_id"],
            "run_id": created["run_id"],
            "kind": "iterate",
            "objective": view["objective"],
            "aux_stats": {"n_scored": view["n_scored"]},
        })
        assert it.status_code == 201

        ckpt = await c.post(f"/api/research/{job['id']}/checkpoint/{created['version_id']}")
        assert ckpt.status_code == 200
        assert ckpt.json()["is_checkpoint"] is True

        restored = (await c.post(f"/api/research/{job['id']}/restore/{created['version_id']}")).json()
        assert restored["version_id"] > created["version_id"]
```

- [ ] **Step 2: Run test — expect PASS**

Run: `pytest tests/test_research_e2e.py -v -s`

- [ ] **Step 3: Commit**

```bash
git add tests/test_research_e2e.py
git commit -m "test(research): end-to-end flow covering job, version, view, iteration, checkpoint, restore"
```

---

## Self-Review Checklist

- **Spec coverage:**
  - Postgres migration (13 SQLite → consolidated) — Task 2
  - `research_jobs`, `research_iterations`, `is_checkpoint`, `runs.date_start/date_end` — Task 3
  - SQL views (solar/moon/combined) — Task 4
  - LISTEN/NOTIFY triggers — Task 5
  - `asyncpg` / `psycopg2` rewrites — Tasks 6, 7, 8
  - Worker LISTEN/NOTIFY with 5s fallback poll — Task 9
  - View endpoint with date filtering — Task 10
  - Research CRUD — Task 11
  - Version endpoint + allowlist — Task 12
  - Iterations, checkpoint, restore — Task 13
  - Server-side Nelder-Mead search — Task 14
  - Cleanup of filesystem stack — Task 15
  - End-to-end test — Task 16

- **Placeholders:** none — every SQL statement, HTTP payload, and file path is concrete.

- **Type consistency:**
  - `view_name` allowlist matches `_ALLOWED_VIEWS` in both `views_routes.py` and `research_routes.py` (`v_solar_position`, `v_moon_position`, `v_combined_position`).
  - `research_iterations.kind` ∈ {`iterate`, `search_eval`, `search_winner`} matched in the validator and in Task 14's insert.
  - `date_start`/`date_end` are `TEXT` everywhere (runs, research_jobs, API bodies); string compare works because catalog dates are ISO-sortable.
  - `auto_queue_runs` signature extended to accept `date_start`/`date_end` and used consistently in Tasks 8, 12, 13, 14.

- **Notes:**
  - Task 8 is the widest mechanical refactor; recommend running the existing API tests continuously while porting.
  - The scanner module (`server/services/scanner.py`) is untouched — it's already DB-agnostic.
  - Phase 2 (admin UI for research jobs) and Phase 3 (websockets, multi-worker) are explicitly out of scope per the spec.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-04-15-research-system-redesign.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — Dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

**Which approach?**
