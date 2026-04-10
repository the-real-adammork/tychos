# Research System Redesign

## Summary

Replace the filesystem-based research simulation system with a DB-driven architecture where the AI researcher creates param versions through the API, relies on the existing worker to execute scans, and reads results through SQL views. Migrate from SQLite to Postgres for LISTEN/NOTIFY real-time coordination between researcher and worker.

## Goals

- Research param changes tracked in the DB like any user would do in the UI
- Researcher relies on the worker process for all scan execution (separation of concerns)
- Declarative "result views" (SQL views) for different optimization targets (sun-only, moon-only, combined)
- Real-time notification when runs complete (Postgres LISTEN/NOTIFY)
- Full version history with checkpoint markers for search winners
- Foundation for future: admin UI for research jobs, researcher daemon, streaming AI reasoning

## Non-Goals (Phase 1)

- Admin UI for creating research jobs (Phase 2)
- Researcher daemon that auto-spawns Claude Code (Phase 2)
- Live browser websocket updates (Phase 3)
- Multi-worker scaling (Phase 3)

---

## Architecture

### Current State

```
AI Agent (Claude Code)
  → edits current.json on disk
  → runs scanner in-process via CLI
  → reads results from scanner output
  → logs to JSONL on disk
  
Worker (separate process)
  → polls SQLite for queued runs
  → runs scanner, writes eclipse_results to SQLite
  
Admin UI
  → talks to FastAPI → SQLite
```

Research and the admin/worker systems are completely separate. Research results never enter the DB. Parameters live in two places (filesystem for research, DB for everything else).

### Target State

```
AI Agent (Claude Code)
  → reads research job config from API
  → creates param versions via API (auto-queues runs)
  → waits for NOTIFY (or polls) for run completion
  → reads results via view API endpoint
  → logs iterations via API
  
Worker (separate process)
  → listens for NOTIFY on Postgres (fallback: 5s poll)
  → runs scanner, writes eclipse_results to Postgres
  → fires NOTIFY on completion
  
Admin UI
  → talks to FastAPI → Postgres
  → same tables, same data, research results visible alongside manual runs
```

One system. Research iterations are param versions. Research results are runs. Everything in Postgres.

---

## Database Changes

### Migration: SQLite to Postgres

All 13 existing SQLite migrations consolidated into a single Postgres-native initial schema. Key differences:
- `AUTOINCREMENT` → `SERIAL` / `GENERATED ALWAYS AS IDENTITY`
- `TEXT` dates stay as `TEXT` (not worth converting to `TIMESTAMPTZ` — Julian Day is the real timestamp)
- `REAL` → `DOUBLE PRECISION` where precision matters (RA/Dec radians)
- `JSON` columns → `JSONB`
- Foreign key `ON DELETE CASCADE` preserved
- WAL mode not needed (Postgres handles concurrency natively)

App code changes:
- `aiosqlite` → `asyncpg` in FastAPI async routes
- `sqlite3` → `psycopg2` in synchronous worker
- `get_db()` / `get_async_db()` context managers rewritten for Postgres connection pooling
- `?` placeholders → `$1, $2, ...` (asyncpg) or `%s` (psycopg2)
- `INSERT OR IGNORE` → `INSERT ... ON CONFLICT DO NOTHING`

### New Tables

```sql
CREATE TABLE research_jobs (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    param_set_id INTEGER NOT NULL REFERENCES param_sets(id),
    dataset_id INTEGER NOT NULL REFERENCES datasets(id),
    view_name TEXT NOT NULL,              -- references a SQL view (e.g. 'v_solar_position')
    allowlist TEXT[] NOT NULL,            -- parameter glob patterns (e.g. '{sun.*,sun_def.*}')
    date_start TEXT,                      -- optional: filter eclipses to this date range (ISO 8601)
    date_end TEXT,                        -- e.g. '1900-01-01' to '2050-12-31'
    status TEXT NOT NULL DEFAULT 'active', -- 'active', 'paused', 'completed'
    instructions TEXT,                    -- rendered program.md content
    created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    updated_at TEXT
);

CREATE TABLE research_iterations (
    id SERIAL PRIMARY KEY,
    research_job_id INTEGER NOT NULL REFERENCES research_jobs(id),
    param_version_id INTEGER NOT NULL REFERENCES param_versions(id),
    run_id INTEGER REFERENCES runs(id),
    kind TEXT NOT NULL,                   -- 'iterate', 'search_eval', 'search_winner'
    objective DOUBLE PRECISION,
    aux_stats JSONB,                      -- {mean_sun_error_arcmin, mean_moon_error_arcmin, n_total, ...}
    created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP)
);
```

### Modified Tables

```sql
-- param_versions gains checkpoint flag
ALTER TABLE param_versions ADD COLUMN is_checkpoint BOOLEAN NOT NULL DEFAULT FALSE;

-- runs gain optional date range for filtered scans
ALTER TABLE runs ADD COLUMN date_start TEXT;
ALTER TABLE runs ADD COLUMN date_end TEXT;
```

### LISTEN/NOTIFY Triggers

```sql
-- Notify when a run is queued (worker wakes up)
CREATE FUNCTION notify_run_queued() RETURNS trigger AS $$
BEGIN
    IF NEW.status = 'queued' THEN
        PERFORM pg_notify('run_queued', NEW.id::text);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_run_queued
    AFTER INSERT OR UPDATE ON runs
    FOR EACH ROW EXECUTE FUNCTION notify_run_queued();

-- Notify when a run completes or fails (researcher wakes up)
CREATE FUNCTION notify_run_completed() RETURNS trigger AS $$
BEGIN
    IF NEW.status IN ('done', 'failed') AND (OLD.status IS NULL OR OLD.status != NEW.status) THEN
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

---

## SQL Views

Three initial views. Each has `run_id`, per-eclipse detail columns, and a computed `error` column. The API endpoint queries these by name.

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

Adding a new view = one migration with a `CREATE VIEW` statement. The API endpoint validates the view name against a whitelist of known views.

### Date Filtering

Date filtering applies at two levels:

**1. View query (API-side):** The view endpoint applies the research job's `date_start`/`date_end` as a WHERE clause on the view query:
```sql
SELECT * FROM v_solar_position
WHERE run_id = $1
  AND date >= $2 AND date <= $3
ORDER BY error DESC
```
The objective (`AVG(error)`) is also computed over only the filtered rows. This means two research jobs with different date ranges produce different objectives from the same run — the view is a lens, not a copy.

**2. Run-level (scanner-side):** When a research job has date filters, the runs it queues should only scan eclipses within that range. This saves scanner time — scanning 200 eclipses (1900–2000) instead of 452 (full catalog).

Implementation: the `runs` table gains optional `date_start`/`date_end` columns. When the research version endpoint (`POST /api/research/{job_id}/version`) creates a run, it copies the job's date range to the run. The worker filters the eclipse catalog to that range before calling the scanner:
```python
eclipses = load_eclipse_catalog(dataset_id)
if run_date_start:
    eclipses = [e for e in eclipses if run_date_start <= e["date"] <= run_date_end]
```

Non-research runs (created via `POST /api/runs`) have NULL date filters and scan the full catalog as today.

---

## API Endpoints

### View Endpoint

```
GET /api/results/{run_id}/view/{view_name}
```

Returns:
```json
{
    "objective": 12.34,
    "n_scored": 450,
    "detail": [
        {
            "date": "1903-09-21T04:39:52",
            "catalog_type": "partial",
            "error": 27.25,
            "sun_delta_ra_arcmin": 23.32,
            "sun_delta_dec_arcmin": -14.09
        }
    ]
}
```

- `objective` = `AVG(error)` from the view for this run_id
- `detail` = all rows from the view for this run_id, sorted by `error DESC` (worst first)
- View name validated against whitelist; 404 if unknown

### Research Endpoints

```
GET    /api/research                         -- list all research jobs
POST   /api/research                         -- create a research job
GET    /api/research/{job_id}                -- get job config + rendered instructions
PATCH  /api/research/{job_id}                -- update status (pause/complete)

GET    /api/research/{job_id}/iterations     -- list iterations (with objective history)
POST   /api/research/{job_id}/iterations     -- log an iteration

POST   /api/research/{job_id}/checkpoint/{version_id}  -- mark version as checkpoint
POST   /api/research/{job_id}/restore/{version_id}     -- create new version from checkpoint's params
POST   /api/research/{job_id}/search                   -- run server-side Nelder-Mead search
```

### Modified Existing Endpoints

```
POST /api/params/{id}/version
```
- Unchanged behavior: creates version, auto-queues runs
- New: accepts optional `is_checkpoint` boolean

---

## Research Workflow (Phase 1)

### Creating a Research Job

Human (or future admin UI) creates a research job via API:
```json
POST /api/research
{
    "name": "solar-sim-03",
    "param_set_id": 5,
    "dataset_id": 1,
    "view_name": "v_solar_position",
    "allowlist": ["sun.*", "sun_def.*", "earth.*"],
    "date_start": "1900-01-01",
    "date_end": "2050-12-31"
}
```

Date filters are optional — omit them to use the full catalog.

The API renders instructions from a template (Tychos model background, parameter guidance, the specific allowlist/view/dataset) and stores them in `research_jobs.instructions`.

### Researcher Flow (Claude Code, manually launched)

1. `GET /api/research/{job_id}` → read instructions, allowlist, view_name, param_set_id
2. `GET /api/params/{param_set_id}` → read latest checkpoint version (or latest version)
3. Edit params, `POST /api/params/{param_set_id}/version` with new params_json → get `version_id`, `run_id`
4. Poll `GET /api/runs/{run_id}` until status=done (or use NOTIFY in future)
5. `GET /api/results/{run_id}/view/{view_name}` → objective + per-eclipse detail
6. `POST /api/research/{job_id}/iterations` → log the iteration
7. If improved: `POST /api/research/{job_id}/checkpoint/{version_id}`
8. If worse: `POST /api/research/{job_id}/restore/{last_checkpoint_version_id}` → new version from checkpoint, continue from there
9. Repeat

### Nelder-Mead Search (Server-Side)

The researcher can also invoke a server-side Nelder-Mead search for coupled parameters:

```
POST /api/research/{job_id}/search
{
    "param_keys": ["sun.start_pos", "sun.speed", "sun_def.start_pos"],
    "budget": 60,
    "scale": 0.01
}
```

The server runs the search internally:
- Runs the scanner in-process (no queue overhead — same as the old CLI search)
- Creates a `param_version` row for each evaluation (marked `kind='search_eval'`)
- Does NOT create `eclipse_results` for intermediate evaluations (speed)
- Computes objectives by querying the job's SQL view against in-memory results
- When done, the winning params get a real version + queued run through the worker for full persisted results (marked `kind='search_winner'` + checkpoint)

Returns:
```json
{
    "starting_objective": 62.28,
    "best_objective": 41.15,
    "delta": -21.13,
    "improved": true,
    "n_evals": 58,
    "winner_version_id": 234,
    "winner_run_id": 567
}
```

The researcher chooses between:
- **Manual iteration** (steps 1–9 above) — for exploration, hypothesis-driven tuning, and reading per-eclipse patterns to inform strategy
- **Server-side search** — for mechanical grinding of coupled parameters once the researcher knows which ones matter and at what scale

### Allowlist Validation

A new research-specific endpoint handles version creation with allowlist enforcement:

```
POST /api/research/{job_id}/version
```

This creates a param version under the job's param set, validates the diff against the job's allowlist (comparing to the last checkpoint), auto-queues a run for the job's dataset, and returns the `version_id` + `run_id`. Returns 400 if non-allowlisted fields are touched.

The existing `POST /api/params/{id}/version` remains unchanged for non-research use (no allowlist enforcement). The researcher always goes through the research-specific endpoint.

---

## Worker Changes

### Postgres Connection

- `sqlite3` → `psycopg2`
- Connection pooling via `psycopg2.pool.SimpleConnectionPool` (min=1, max=3)

### LISTEN/NOTIFY

On startup:
```python
conn = pool.getconn()
conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
conn.execute("LISTEN run_queued")
```

Main loop:
```python
while True:
    if select.select([conn], [], [], 5.0) == ([], [], []):
        # timeout — fallback poll
        pass
    conn.poll()
    while conn.notifies:
        notify = conn.notifies.pop(0)
        # process the run
    _process_one()
```

### Scanner + Enrichment

Unchanged. The scanner is database-agnostic (takes params + eclipses, returns dicts). The worker's enrichment logic (computing deltas, tychos_error_arcmin, etc.) stays the same — just writes to Postgres instead of SQLite.

---

## What Gets Deleted

The entire filesystem-based research system:
- `server/research/cli.py` — replaced by API endpoints
- `server/research/__main__.py` — no CLI entry point needed
- `server/research/sandbox.py` — no filesystem job directories
- `server/research/subset.py` — full catalog always (loaded from DB)
- `server/research/program_md.py` — instructions rendered by API from template
- `server/research/allowlist.py` — validation moves to API endpoint
- `server/research/objective.py` — replaced by SQL views + `AVG(error)`
- `server/research/search.py` — Nelder-Mead logic moves to the search API endpoint (`POST /api/research/{job_id}/search`)
- `research.sh` — no wrapper needed
- `params/research/*/` — all filesystem artifacts (baseline.json, current.json, subset.json, program.md, log.jsonl)
- Templates directory for program.md rendering

The `server/research/` directory becomes either empty or contains just the template for rendering instructions.

---

## Phasing

### Phase 1: Foundation

**Database:**
- Postgres migration (consolidated schema from 13 SQLite migrations)
- LISTEN/NOTIFY triggers
- SQL views (v_solar_position, v_moon_position, v_combined_position)
- `research_jobs` + `research_iterations` tables
- `is_checkpoint` on `param_versions`

**API:**
- View endpoint: `GET /api/results/{run_id}/view/{view_name}`
- Research CRUD endpoints
- Allowlist validation on version creation
- Checkpoint + restore endpoints

**Worker:**
- Postgres connection (psycopg2)
- LISTEN/NOTIFY subscription (with 5s fallback poll)
- NOTIFY on run completion

**Researcher:**
- Thin CLI wrapper that reads job from API, renders program.md
- Manual launch: human runs Claude Code with rendered instructions
- Claude Code talks to API for all operations

**Cleanup:**
- Delete `server/research/` filesystem-based code
- Delete `params/research/` job directories
- Delete `research.sh`

### Phase 2: Admin UI + Researcher Daemon

- Admin pages for creating/managing research jobs
  - Pick param set, dataset, view, allowlist from dropdowns
  - Research job dashboard: iteration history, objective-over-time chart, checkpoint timeline
- Researcher worker daemon
  - Watches `research_jobs` table for active jobs
  - Spawns Claude Code subprocess per job
  - Captures Claude Code output to `research_iterations` or a `research_logs` table
  - Wall-clock budget enforcement (kills subprocess after N hours or on no improvement)

### Phase 3: Polish

- Live browser updates via FastAPI websocket bridging NOTIFY
- Version diff view (compare any two versions' params side-by-side)
- Research job templates (pre-configured allowlists + views)
- Multi-worker scaling (advisory locks on run pickup to prevent double-processing)

---

## Testing Strategy

### Phase 1

- **DB migration:** golden-file test — dump SQLite schema + seed data, migrate to Postgres, verify row counts and key queries match
- **SQL views:** unit tests — insert known eclipse_results rows, query each view, assert error computation matches Python reference
- **API endpoints:** integration tests for view endpoint, research CRUD, checkpoint/restore, allowlist validation
- **Worker NOTIFY:** integration test — insert a queued run, verify worker picks it up via NOTIFY within 1s (vs 5s poll)
- **End-to-end:** create research job, create version, wait for run, read view, verify objective matches expected value

### Existing Tests

Scanner tests, objective tests, and smoke tests that test the old CLI flow will need to be rewritten or deleted. Scanner tests are database-agnostic and stay. The research smoke tests (`tests/research/test_smoke.py`) get replaced by API integration tests.
