# Researcher Daemon Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an autonomous research agent that runs as async tasks inside the FastAPI server, driving Claude Agent SDK conversations to iteratively optimize Tychos orbital parameters with pause/inject/resume support and full conversation logging.

**Architecture:** Each active research job gets one `asyncio.Task` running a Claude SDK tool-use loop. Claude has tools (`propose_params`, `checkpoint`, `restore`, `search`) that call into existing research endpoints internally. Between SDK turns, the task checks budgets (iterations, wall-clock, plateau), reads user-injected messages from a DB queue, and logs every event to `research_logs` for replay/streaming. A `ResearcherManager` singleton tracks running tasks and handles start/pause/resume/crash-recovery.

**Tech Stack:** Anthropic Python SDK (`anthropic`), asyncpg, FastAPI SSE via `sse-starlette`, existing Postgres schema + worker.

---

## File Structure

**Created:**
- `server/migrations/pg/005_researcher.sql` — new tables + altered columns + NOTIFY trigger
- `server/researcher/__init__.py` — empty
- `server/researcher/tools.py` — tool JSON schemas + async execution functions
- `server/researcher/session.py` — `run_research_session()` async: SDK loop, budget, logging, injection
- `server/researcher/manager.py` — `ResearcherManager`: task lifecycle, start/stop/resume, crash recovery
- `tests/test_researcher_tools.py` — unit tests for tool execution
- `tests/test_researcher_session.py` — session tests with mocked SDK
- `tests/test_researcher_api.py` — integration tests for control endpoints
- `tests/test_researcher_e2e.py` — full flow with real SDK (manual, requires API key)

**Modified:**
- `requirements.txt` — add `anthropic`, `sse-starlette`
- `server/api/research_routes.py` — new control endpoints + extend `CreateJobBody`
- `server/app.py` — lifespan crash recovery via manager
- `local_deploy/.env.example` — `ANTHROPIC_API_KEY`
- `start-server.sh` — optional `ANTHROPIC_API_KEY` guard

---

## Task 1: Migration + dependencies

**Files:**
- Create: `server/migrations/pg/005_researcher.sql`
- Modify: `requirements.txt`
- Modify: `local_deploy/.env.example`

- [ ] **Step 1: Write `server/migrations/pg/005_researcher.sql`**

```sql
CREATE TABLE research_logs (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    research_job_id INTEGER NOT NULL REFERENCES research_jobs(id) ON DELETE CASCADE,
    research_iteration_id INTEGER REFERENCES research_iterations(id),
    role TEXT NOT NULL,
    content TEXT,
    tool_name TEXT,
    token_count INTEGER,
    created_at TEXT NOT NULL DEFAULT (to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS'))
);

CREATE INDEX idx_research_logs_job ON research_logs(research_job_id, created_at);

CREATE TABLE research_messages (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    research_job_id INTEGER NOT NULL REFERENCES research_jobs(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    consumed BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TEXT NOT NULL DEFAULT (to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS'))
);

CREATE INDEX idx_research_messages_job ON research_messages(research_job_id, consumed);

ALTER TABLE research_jobs ADD COLUMN model TEXT NOT NULL DEFAULT 'claude-sonnet-4-6';
ALTER TABLE research_jobs ADD COLUMN max_iterations INTEGER NOT NULL DEFAULT 40;
ALTER TABLE research_jobs ADD COLUMN max_wall_clock_seconds INTEGER NOT NULL DEFAULT 3600;
ALTER TABLE research_jobs ADD COLUMN no_improvement_plateau INTEGER NOT NULL DEFAULT 6;
ALTER TABLE research_jobs ADD COLUMN current_iteration INTEGER NOT NULL DEFAULT 0;
ALTER TABLE research_jobs ADD COLUMN iterations_since_checkpoint INTEGER NOT NULL DEFAULT 0;
ALTER TABLE research_jobs ADD COLUMN session_started_at TEXT;

CREATE OR REPLACE FUNCTION notify_research_log_append() RETURNS trigger AS $$
BEGIN
    PERFORM pg_notify('research_log_append',
        json_build_object('job_id', NEW.research_job_id, 'log_id', NEW.id, 'role', NEW.role)::text);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_research_log_append
    AFTER INSERT ON research_logs
    FOR EACH ROW EXECUTE FUNCTION notify_research_log_append();
```

- [ ] **Step 2: Update `requirements.txt`**

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
anthropic
sse-starlette
```

- [ ] **Step 3: Update `local_deploy/.env.example`**

Append after the Postgres section:
```
# Anthropic API (required for researcher daemon)
ANTHROPIC_API_KEY=sk-ant-...
```

- [ ] **Step 4: Install deps + apply migration**

```bash
source tychos_skyfield/.venv/bin/activate
pip install -r requirements.txt
python -c "import anthropic; print('anthropic', anthropic.__version__)"
python -c "from sse_starlette.sse import EventSourceResponse; print('sse ok')"
psql "$DATABASE_URL" -f server/migrations/pg/005_researcher.sql
psql "$DATABASE_URL" -c "\d research_logs" -c "\d research_messages" -c "\d research_jobs"
```

- [ ] **Step 5: Commit**

```bash
git add server/migrations/pg/005_researcher.sql requirements.txt local_deploy/.env.example
git commit -m "feat(db): add researcher tables, messages queue, and log trigger"
```

---

## Task 2: Tool definitions and execution

**Files:**
- Create: `server/researcher/__init__.py`
- Create: `server/researcher/tools.py`
- Create: `tests/test_researcher_tools.py`

The tools module defines JSON schemas for the SDK and async functions that execute each tool against the DB. These are pure async functions — no SDK dependency, no session state. They can be tested independently.

- [ ] **Step 1: Write failing test `tests/test_researcher_tools.py`**

```python
import json
import pytest
import pytest_asyncio
import asyncio

import server.db as _dbmod
from server.db import init_db, get_db, get_async_db


@pytest.fixture(autouse=True, scope="module")
def _init():
    import psycopg2
    from server.db import DATABASE_URL
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;")
    conn.close()
    init_db()


@pytest_asyncio.fixture(autouse=True)
async def _reset_async_pool():
    pool = _dbmod._async_pool
    if pool is not None:
        try:
            await pool.close()
        except Exception:
            pass
        _dbmod._async_pool = None
    yield
    pool = _dbmod._async_pool
    if pool is not None:
        try:
            await pool.close()
        except Exception:
            pass
        _dbmod._async_pool = None


@pytest.fixture
def research_job_id():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM param_sets ORDER BY id LIMIT 1")
            ps_id = cur.fetchone()[0]
            cur.execute("SELECT id FROM datasets ORDER BY id LIMIT 1")
            ds_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO research_jobs (name, param_set_id, dataset_id, view_name, allowlist, date_start, date_end) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                ("tool-test", ps_id, ds_id, "v_solar_position", ["sun.*"], "1950-01-01", "1952-12-31"),
            )
            job_id = cur.fetchone()[0]
        conn.commit()
    return job_id


@pytest.mark.asyncio
async def test_tool_schemas_are_valid():
    from server.researcher.tools import TOOL_SCHEMAS
    assert len(TOOL_SCHEMAS) == 4
    names = {t["name"] for t in TOOL_SCHEMAS}
    assert names == {"propose_params", "checkpoint", "restore", "search"}
    for t in TOOL_SCHEMAS:
        assert "input_schema" in t
        assert t["input_schema"]["type"] == "object"


@pytest.mark.asyncio
async def test_propose_params_validates_allowlist(research_job_id):
    from server.researcher.tools import execute_tool
    result = await execute_tool("propose_params", {"params_json": '{"moon": {"start_pos": 999}}'}, research_job_id)
    assert "error" in result.lower() or "allowlist" in result.lower()


@pytest.mark.asyncio
async def test_checkpoint_marks_version(research_job_id):
    from server.researcher.tools import execute_tool
    async with get_async_db() as conn:
        v_id = await conn.fetchval(
            "SELECT id FROM param_versions WHERE param_set_id=(SELECT param_set_id FROM research_jobs WHERE id=$1) ORDER BY version_number DESC LIMIT 1",
            research_job_id,
        )
    result = await execute_tool("checkpoint", {"version_id": v_id}, research_job_id)
    assert "ok" in result.lower() or "true" in result.lower()
    async with get_async_db() as conn:
        row = await conn.fetchrow("SELECT is_checkpoint FROM param_versions WHERE id=$1", v_id)
    assert row["is_checkpoint"] is True
```

- [ ] **Step 2: Run test — expect FAIL (module doesn't exist)**

```bash
DATABASE_URL=postgres://tychos:tychos@localhost:5432/tychos_research_redesign_test TYCHOS_ADMIN_USER=admin@t.local TYCHOS_ADMIN_PASSWORD=pw PYTHONPATH=tychos_skyfield:tests:. pytest tests/test_researcher_tools.py -v
```

- [ ] **Step 3: Create `server/researcher/__init__.py`**

```python
"""Autonomous researcher daemon: SDK sessions, tools, and task management."""
```

- [ ] **Step 4: Implement `server/researcher/tools.py`**

```python
"""Tool definitions and execution for the researcher SDK session.

Each tool maps to an existing research API operation. Execution is async
and talks directly to the DB (not via HTTP) for lower latency.
"""
import hashlib
import json
import math
import asyncio

from server.db import get_async_db
from server.research.allowlist import check_diff_against_allowlist, AllowlistViolation, expand_globs
from server.research.search_engine import run_search

TOOL_SCHEMAS = [
    {
        "name": "propose_params",
        "description": (
            "Propose new parameter values. Validates against the job's allowlist, "
            "creates a new param version, waits for the worker to run the scanner, "
            "and returns the objective + per-eclipse error detail."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "params_json": {
                    "type": "string",
                    "description": "JSON string of the full params dict with your proposed changes",
                },
            },
            "required": ["params_json"],
        },
    },
    {
        "name": "checkpoint",
        "description": "Mark a param version as a checkpoint (best known state). Resets the no-improvement counter.",
        "input_schema": {
            "type": "object",
            "properties": {
                "version_id": {"type": "integer", "description": "The param_version id to checkpoint"},
            },
            "required": ["version_id"],
        },
    },
    {
        "name": "restore",
        "description": (
            "Create a new version from a checkpoint's params and run the scanner. "
            "Use this to revert to a known good state after failed exploration."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "version_id": {"type": "integer", "description": "The checkpoint version_id to restore from"},
            },
            "required": ["version_id"],
        },
    },
    {
        "name": "search",
        "description": (
            "Run server-side Nelder-Mead optimization over 2-6 coupled parameters. "
            "Use when you've identified which params matter and want to grind them mechanically."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "param_keys": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of body.field keys to optimize (e.g. ['sun.start_pos', 'sun.speed'])",
                },
                "budget": {"type": "integer", "description": "Max evaluations (default 20)", "default": 20},
                "scale": {"type": "number", "description": "Initial simplex step fraction (default 0.01)", "default": 0.01},
            },
            "required": ["param_keys"],
        },
    },
]


async def execute_tool(tool_name: str, tool_input: dict, job_id: int) -> str:
    """Execute a tool and return a JSON string result for the SDK."""
    try:
        if tool_name == "propose_params":
            return await _propose_params(job_id, tool_input["params_json"])
        elif tool_name == "checkpoint":
            return await _checkpoint(job_id, tool_input["version_id"])
        elif tool_name == "restore":
            return await _restore(job_id, tool_input["version_id"])
        elif tool_name == "search":
            return await _search(
                job_id,
                tool_input["param_keys"],
                tool_input.get("budget", 20),
                tool_input.get("scale", 0.01),
            )
        else:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


async def _get_job(conn, job_id: int):
    return await conn.fetchrow("SELECT * FROM research_jobs WHERE id=$1", job_id)


async def _get_baseline(conn, param_set_id: int) -> dict:
    row = await conn.fetchrow(
        "SELECT params_json FROM param_versions WHERE param_set_id=$1 AND is_checkpoint=TRUE ORDER BY version_number DESC LIMIT 1",
        param_set_id,
    )
    if row is None:
        row = await conn.fetchrow(
            "SELECT params_json FROM param_versions WHERE param_set_id=$1 ORDER BY version_number ASC LIMIT 1",
            param_set_id,
        )
    return json.loads(row["params_json"])


async def _wait_for_run(run_id: int, timeout: float = 300.0) -> str:
    """Poll until run is done or failed. Returns status string."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        async with get_async_db() as conn:
            row = await conn.fetchrow("SELECT status FROM runs WHERE id=$1", run_id)
        if row and row["status"] in ("done", "failed"):
            return row["status"]
        await asyncio.sleep(2.0)
    return "timeout"


async def _get_view_result(run_id: int, view_name: str, full_detail: bool = False) -> dict:
    """Query the view for a completed run. Returns {objective, n_scored, detail}."""
    async with get_async_db() as conn:
        run = await conn.fetchrow("SELECT date_start, date_end FROM runs WHERE id=$1", run_id)
        filters = ["run_id = $1"]
        args: list = [run_id]
        if run["date_start"]:
            filters.append(f"date >= ${len(args)+1}")
            args.append(run["date_start"])
        if run["date_end"]:
            filters.append(f"date <= ${len(args)+1}")
            args.append(run["date_end"])
        where = " AND ".join(filters)
        obj = await conn.fetchrow(
            f"SELECT AVG(error) AS objective, COUNT(*) AS n FROM {view_name} WHERE {where}", *args
        )
        if full_detail:
            rows = await conn.fetch(f"SELECT * FROM {view_name} WHERE {where} ORDER BY error DESC", *args)
        else:
            rows = await conn.fetch(f"SELECT * FROM {view_name} WHERE {where} ORDER BY error DESC LIMIT 10", *args)
    return {
        "objective": float(obj["objective"]) if obj["objective"] is not None else None,
        "n_scored": int(obj["n"]),
        "detail": [dict(r) for r in rows],
    }


async def _propose_params(job_id: int, params_json_str: str) -> str:
    async with get_async_db() as conn:
        job = await _get_job(conn, job_id)
        baseline = await _get_baseline(conn, job["param_set_id"])

        try:
            new_params = json.loads(params_json_str)
        except Exception as exc:
            return json.dumps({"error": f"Invalid JSON: {exc}"})

        try:
            check_diff_against_allowlist(
                new_params, baseline,
                allowlist_globs=list(job["allowlist"]),
                known_bodies=list(baseline.keys()),
            )
        except AllowlistViolation as exc:
            return json.dumps({"error": f"Allowlist violation: {exc}"})

        latest_num = await conn.fetchval(
            "SELECT COALESCE(MAX(version_number),0) FROM param_versions WHERE param_set_id=$1",
            job["param_set_id"],
        )
        md5 = hashlib.md5(json.dumps(new_params, sort_keys=True).encode()).hexdigest()
        version_id = await conn.fetchval(
            "INSERT INTO param_versions (param_set_id, version_number, params_md5, params_json, notes) "
            "VALUES ($1,$2,$3,$4,$5) RETURNING id",
            job["param_set_id"], latest_num + 1, md5, params_json_str, "researcher agent iteration",
        )
        run_id = await conn.fetchval(
            "INSERT INTO runs (param_version_id, dataset_id, status, date_start, date_end) "
            "VALUES ($1,$2,'queued',$3,$4) RETURNING id",
            version_id, job["dataset_id"], job["date_start"], job["date_end"],
        )

    status = await _wait_for_run(run_id)
    if status != "done":
        return json.dumps({"error": f"Run {run_id} {status}", "version_id": version_id, "run_id": run_id})

    view = await _get_view_result(run_id, job["view_name"], full_detail=False)
    return json.dumps({
        "version_id": version_id,
        "run_id": run_id,
        **view,
    })


async def _checkpoint(job_id: int, version_id: int) -> str:
    async with get_async_db() as conn:
        job = await _get_job(conn, job_id)
        v = await conn.fetchrow(
            "SELECT id FROM param_versions WHERE id=$1 AND param_set_id=$2",
            version_id, job["param_set_id"],
        )
        if not v:
            return json.dumps({"error": f"Version {version_id} not found on this job's param set"})
        await conn.execute("UPDATE param_versions SET is_checkpoint=TRUE WHERE id=$1", version_id)

    view = await _get_view_result_for_version(version_id, job["view_name"])
    return json.dumps({"ok": True, "version_id": version_id, **(view or {})})


async def _get_view_result_for_version(version_id: int, view_name: str) -> dict | None:
    """Get full view detail for the latest done run of a version."""
    async with get_async_db() as conn:
        run = await conn.fetchrow(
            "SELECT id FROM runs WHERE param_version_id=$1 AND status='done' ORDER BY completed_at DESC LIMIT 1",
            version_id,
        )
    if not run:
        return None
    return await _get_view_result(run["id"], view_name, full_detail=True)


async def _restore(job_id: int, version_id: int) -> str:
    async with get_async_db() as conn:
        job = await _get_job(conn, job_id)
        src = await conn.fetchrow(
            "SELECT params_json FROM param_versions WHERE id=$1 AND param_set_id=$2",
            version_id, job["param_set_id"],
        )
        if not src:
            return json.dumps({"error": f"Version {version_id} not found on this job's param set"})
        params_json = src["params_json"]
        md5 = hashlib.md5(json.dumps(json.loads(params_json), sort_keys=True).encode()).hexdigest()
        latest_num = await conn.fetchval(
            "SELECT COALESCE(MAX(version_number),0) FROM param_versions WHERE param_set_id=$1",
            job["param_set_id"],
        )
        new_vid = await conn.fetchval(
            "INSERT INTO param_versions (param_set_id, version_number, parent_version_id, params_md5, params_json, notes) "
            "VALUES ($1,$2,$3,$4,$5,$6) RETURNING id",
            job["param_set_id"], latest_num + 1, version_id, md5, params_json, f"restored from v{version_id}",
        )
        run_id = await conn.fetchval(
            "INSERT INTO runs (param_version_id, dataset_id, status, date_start, date_end) "
            "VALUES ($1,$2,'queued',$3,$4) RETURNING id",
            new_vid, job["dataset_id"], job["date_start"], job["date_end"],
        )

    status = await _wait_for_run(run_id)
    if status != "done":
        return json.dumps({"error": f"Run {run_id} {status}", "version_id": new_vid, "run_id": run_id})

    view = await _get_view_result(run_id, job["view_name"], full_detail=True)
    return json.dumps({"version_id": new_vid, "run_id": run_id, **view})


async def _search(job_id: int, param_keys: list[str], budget: int, scale: float) -> str:
    async with get_async_db() as conn:
        job = await _get_job(conn, job_id)
        baseline = await _get_baseline(conn, job["param_set_id"])
        allowed = expand_globs(list(job["allowlist"]), list(baseline.keys()))
        forbidden = [k for k in param_keys if k not in allowed]
        if forbidden:
            return json.dumps({"error": f"param_keys not in allowlist: {forbidden}"})

        ds = await conn.fetchrow("SELECT slug, scan_window_hours FROM datasets WHERE id=$1", job["dataset_id"])
        jpl_rows = await conn.fetch(
            "SELECT julian_day_tt, best_jd, sun_ra_rad, sun_dec_rad, moon_ra_rad, moon_dec_rad "
            "FROM jpl_reference WHERE dataset_id=$1",
            job["dataset_id"],
        )
        cat_filters = ["dataset_id=$1"]
        cat_args: list = [job["dataset_id"]]
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

    from server.services.scanner import scan_solar_eclipses, scan_lunar_eclipses

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
                errs.append(math.sqrt(s_dra**2 + s_ddec**2))
            else:
                m_dra = (r["tychos_moon_ra_at_jpl_rad"] - jpl["moon_ra_rad"]) * cos_m * RAD_TO_ARCMIN
                m_ddec = (r["tychos_moon_dec_at_jpl_rad"] - jpl["moon_dec_rad"]) * RAD_TO_ARCMIN
                if job["view_name"] == "v_moon_position":
                    errs.append(math.sqrt(m_dra**2 + m_ddec**2))
                else:
                    errs.append(math.sqrt(s_dra**2 + s_ddec**2 + m_dra**2 + m_ddec**2))
        return float("inf") if not errs else sum(errs) / len(errs)

    search_result = await asyncio.to_thread(
        run_search,
        current=baseline,
        param_keys=param_keys,
        evaluate=_evaluate,
        budget=budget,
        scale=scale,
    )

    improved = search_result.best_objective < search_result.starting_objective
    winner_version_id = None
    winner_run_id = None

    if improved:
        async with get_async_db() as conn:
            latest_num = await conn.fetchval(
                "SELECT COALESCE(MAX(version_number),0) FROM param_versions WHERE param_set_id=$1",
                job["param_set_id"],
            )
            pj = json.dumps(search_result.best_params, sort_keys=True)
            md5 = hashlib.md5(pj.encode()).hexdigest()
            winner_version_id = await conn.fetchval(
                "INSERT INTO param_versions (param_set_id, version_number, params_md5, params_json, notes, is_checkpoint) "
                "VALUES ($1,$2,$3,$4,$5,TRUE) RETURNING id",
                job["param_set_id"], latest_num + 1, md5, pj,
                f"search winner: {param_keys} (budget {budget})",
            )
            winner_run_id = await conn.fetchval(
                "INSERT INTO runs (param_version_id, dataset_id, status, date_start, date_end) "
                "VALUES ($1,$2,'queued',$3,$4) RETURNING id",
                winner_version_id, job["dataset_id"], job["date_start"], job["date_end"],
            )

    return json.dumps({
        "starting_objective": search_result.starting_objective,
        "best_objective": search_result.best_objective,
        "delta": search_result.best_objective - search_result.starting_objective,
        "improved": improved,
        "n_evals": search_result.n_evals,
        "winner_version_id": winner_version_id,
        "winner_run_id": winner_run_id,
    })
```

- [ ] **Step 5: Run tests — expect PASS**

```bash
DATABASE_URL=postgres://tychos:tychos@localhost:5432/tychos_research_redesign_test TYCHOS_ADMIN_USER=admin@t.local TYCHOS_ADMIN_PASSWORD=pw PYTHONPATH=tychos_skyfield:tests:. pytest tests/test_researcher_tools.py -v
```

- [ ] **Step 6: Commit**

```bash
git add server/researcher/ tests/test_researcher_tools.py
git commit -m "feat(researcher): tool definitions and execution functions"
```

---

## Task 3: Session runner

**Files:**
- Create: `server/researcher/session.py`
- Create: `tests/test_researcher_session.py`

The session runner is the core loop: create SDK client → stream turns → execute tools → check budget → check injections → log everything.

- [ ] **Step 1: Write failing test `tests/test_researcher_session.py`**

```python
import json
import pytest
import pytest_asyncio
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import server.db as _dbmod
from server.db import init_db, get_db, get_async_db, DATABASE_URL


@pytest.fixture(autouse=True, scope="module")
def _init():
    import psycopg2
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;")
    conn.close()
    init_db()


@pytest_asyncio.fixture(autouse=True)
async def _reset_async_pool():
    pool = _dbmod._async_pool
    if pool is not None:
        try:
            await pool.close()
        except Exception:
            pass
        _dbmod._async_pool = None
    yield
    pool = _dbmod._async_pool
    if pool is not None:
        try:
            await pool.close()
        except Exception:
            pass
        _dbmod._async_pool = None


@pytest.fixture
def job_id():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM param_sets ORDER BY id LIMIT 1")
            ps_id = cur.fetchone()[0]
            cur.execute("SELECT id FROM datasets ORDER BY id LIMIT 1")
            ds_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO research_jobs (name, param_set_id, dataset_id, view_name, allowlist, "
                "status, max_iterations, max_wall_clock_seconds, no_improvement_plateau, date_start, date_end) "
                "VALUES (%s,%s,%s,%s,%s,'active',3,3600,2,%s,%s) RETURNING id",
                ("session-test", ps_id, ds_id, "v_solar_position", ["sun.*"], "1950-01-01", "1952-12-31"),
            )
            job_id = cur.fetchone()[0]
        conn.commit()
    return job_id


def _make_mock_response(content_blocks, stop_reason="end_turn"):
    """Build a mock Message object matching anthropic SDK shape."""
    response = MagicMock()
    response.content = content_blocks
    response.stop_reason = stop_reason
    response.usage = MagicMock(input_tokens=100, output_tokens=50)
    return response


def _make_text_block(text):
    block = MagicMock()
    block.type = "text"
    block.text = text
    return block


def _make_tool_use_block(tool_id, name, input_dict):
    block = MagicMock()
    block.type = "tool_use"
    block.id = tool_id
    block.name = name
    block.input = input_dict
    return block


@pytest.mark.asyncio
async def test_session_stops_on_budget(job_id):
    """Session with max_iterations=3 should stop after 3 propose_params calls."""
    from server.researcher.session import run_research_session

    call_count = 0

    async def fake_execute_tool(name, input_dict, jid):
        nonlocal call_count
        call_count += 1
        return json.dumps({"objective": 20.0 - call_count, "n_scored": 6, "detail": [], "version_id": call_count, "run_id": call_count})

    # Build a mock SDK that always proposes params
    async def mock_sdk_turn(messages, **kwargs):
        # Read latest params from DB to build a valid proposal
        async with get_async_db() as conn:
            job = await conn.fetchrow("SELECT * FROM research_jobs WHERE id=$1", job_id)
            row = await conn.fetchrow(
                "SELECT params_json FROM param_versions WHERE param_set_id=$1 ORDER BY version_number DESC LIMIT 1",
                job["param_set_id"],
            )
        return _make_mock_response(
            [_make_tool_use_block(f"call_{call_count}", "propose_params", {"params_json": row["params_json"]})],
            stop_reason="tool_use",
        )

    with patch("server.researcher.session._sdk_turn", side_effect=mock_sdk_turn):
        with patch("server.researcher.tools.execute_tool", side_effect=fake_execute_tool):
            await run_research_session(job_id)

    assert call_count == 3

    async with get_async_db() as conn:
        job = await conn.fetchrow("SELECT status, current_iteration FROM research_jobs WHERE id=$1", job_id)
    assert job["status"] == "paused"
    assert job["current_iteration"] == 3


@pytest.mark.asyncio
async def test_session_stops_on_plateau(job_id):
    """Session with no_improvement_plateau=2 should pause after 2 iterations without checkpoint."""
    from server.researcher.session import run_research_session

    call_count = 0

    async def fake_execute_tool(name, input_dict, jid):
        nonlocal call_count
        call_count += 1
        return json.dumps({"objective": 20.0, "n_scored": 6, "detail": [], "version_id": call_count, "run_id": call_count})

    async def mock_sdk_turn(messages, **kwargs):
        async with get_async_db() as conn:
            job = await conn.fetchrow("SELECT * FROM research_jobs WHERE id=$1", job_id)
            row = await conn.fetchrow(
                "SELECT params_json FROM param_versions WHERE param_set_id=$1 ORDER BY version_number DESC LIMIT 1",
                job["param_set_id"],
            )
        return _make_mock_response(
            [_make_tool_use_block(f"call_{call_count}", "propose_params", {"params_json": row["params_json"]})],
            stop_reason="tool_use",
        )

    with patch("server.researcher.session._sdk_turn", side_effect=mock_sdk_turn):
        with patch("server.researcher.tools.execute_tool", side_effect=fake_execute_tool):
            await run_research_session(job_id)

    assert call_count == 2

    async with get_async_db() as conn:
        job = await conn.fetchrow("SELECT status FROM research_jobs WHERE id=$1", job_id)
    assert job["status"] == "paused"


@pytest.mark.asyncio
async def test_session_injects_user_message(job_id):
    """Messages written to research_messages appear in the conversation."""
    from server.researcher.session import run_research_session

    call_count = 0
    injected = False

    async def fake_execute_tool(name, input_dict, jid):
        nonlocal call_count, injected
        call_count += 1
        if call_count == 1 and not injected:
            async with get_async_db() as conn:
                await conn.execute(
                    "INSERT INTO research_messages (research_job_id, content) VALUES ($1, $2)",
                    jid, "Focus on sun.start_pos only",
                )
            injected = True
        return json.dumps({"objective": 20.0, "n_scored": 6, "detail": [], "version_id": call_count, "run_id": call_count})

    messages_seen = []

    original_mock = None

    async def mock_sdk_turn(messages, **kwargs):
        messages_seen.append([m.get("content") if isinstance(m, dict) else m for m in messages])
        async with get_async_db() as conn:
            job = await conn.fetchrow("SELECT * FROM research_jobs WHERE id=$1", job_id)
            row = await conn.fetchrow(
                "SELECT params_json FROM param_versions WHERE param_set_id=$1 ORDER BY version_number DESC LIMIT 1",
                job["param_set_id"],
            )
        return _make_mock_response(
            [_make_tool_use_block(f"call_{call_count}", "propose_params", {"params_json": row["params_json"]})],
            stop_reason="tool_use",
        )

    with patch("server.researcher.session._sdk_turn", side_effect=mock_sdk_turn):
        with patch("server.researcher.tools.execute_tool", side_effect=fake_execute_tool):
            await run_research_session(job_id)

    async with get_async_db() as conn:
        logs = await conn.fetch(
            "SELECT role, content FROM research_logs WHERE research_job_id=$1 AND role='user_inject' ORDER BY id",
            job_id,
        )
    assert len(logs) >= 1
    assert "sun.start_pos" in logs[0]["content"]
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
DATABASE_URL=postgres://tychos:tychos@localhost:5432/tychos_research_redesign_test TYCHOS_ADMIN_USER=admin@t.local TYCHOS_ADMIN_PASSWORD=pw PYTHONPATH=tychos_skyfield:tests:. pytest tests/test_researcher_session.py -v
```

- [ ] **Step 3: Implement `server/researcher/session.py`**

```python
"""Research session runner — the core SDK conversation loop.

Drives a Claude Agent SDK conversation for a research job. Between turns:
checks budget, reads user-injected messages, logs all events.
"""
import json
import os
import time

import anthropic

from server.db import get_async_db
from server.researcher.tools import TOOL_SCHEMAS, execute_tool


async def _sdk_turn(messages: list[dict], *, model: str, system: str, tools: list[dict]) -> "anthropic.types.Message":
    """One SDK round-trip. Separated for easy mocking in tests."""
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    with client.messages.stream(
        model=model,
        max_tokens=4096,
        system=system,
        tools=tools,
        messages=messages,
    ) as stream:
        return stream.get_final_message()


async def _log(conn, job_id: int, role: str, content: str | None, tool_name: str | None = None, token_count: int | None = None, iteration_id: int | None = None):
    await conn.execute(
        "INSERT INTO research_logs (research_job_id, research_iteration_id, role, content, tool_name, token_count) "
        "VALUES ($1,$2,$3,$4,$5,$6)",
        job_id, iteration_id, role, content, tool_name, token_count,
    )


async def _build_initial_context(job_id: int) -> tuple[str, list[dict]]:
    """Build system prompt + initial messages for a fresh session."""
    async with get_async_db() as conn:
        job = await conn.fetchrow("SELECT * FROM research_jobs WHERE id=$1", job_id)
        system = job["instructions"] or ""

        baseline = await conn.fetchrow(
            "SELECT params_json FROM param_versions WHERE param_set_id=$1 AND is_checkpoint=TRUE ORDER BY version_number DESC LIMIT 1",
            job["param_set_id"],
        )
        if baseline is None:
            baseline = await conn.fetchrow(
                "SELECT params_json FROM param_versions WHERE param_set_id=$1 ORDER BY version_number ASC LIMIT 1",
                job["param_set_id"],
            )

        iterations = await conn.fetch(
            "SELECT kind, objective, created_at FROM research_iterations WHERE research_job_id=$1 ORDER BY created_at DESC LIMIT 10",
            job_id,
        )

    history_lines = []
    for it in reversed(list(iterations)):
        history_lines.append(f"  {it['kind']}: objective={it['objective']}")

    snapshot = f"Current checkpoint params:\n```json\n{baseline['params_json']}\n```\n"
    if history_lines:
        snapshot += "\nRecent iteration history:\n" + "\n".join(history_lines) + "\n"
    snapshot += "\nBegin optimizing. Use propose_params to test changes, checkpoint when improved, search for coupled parameters."

    return system, [{"role": "user", "content": snapshot}]


async def _rebuild_conversation(job_id: int) -> tuple[str, list[dict]]:
    """Rebuild conversation from research_logs for resume."""
    async with get_async_db() as conn:
        job = await conn.fetchrow("SELECT * FROM research_jobs WHERE id=$1", job_id)
        system = job["instructions"] or ""
        logs = await conn.fetch(
            "SELECT role, content, tool_name FROM research_logs WHERE research_job_id=$1 ORDER BY created_at ASC, id ASC",
            job_id,
        )

    if not logs:
        return await _build_initial_context(job_id)

    messages: list[dict] = []
    for log in logs:
        if log["role"] == "user_inject":
            messages.append({"role": "user", "content": log["content"]})
        elif log["role"] == "assistant":
            messages.append({"role": "assistant", "content": log["content"]})
        elif log["role"] == "tool_call":
            content = json.loads(log["content"]) if log["content"] else {}
            if not messages or messages[-1]["role"] != "assistant":
                messages.append({"role": "assistant", "content": []})
            if isinstance(messages[-1]["content"], str):
                messages[-1]["content"] = [{"type": "text", "text": messages[-1]["content"]}]
            messages[-1]["content"].append({
                "type": "tool_use",
                "id": content.get("tool_use_id", "unknown"),
                "name": log["tool_name"],
                "input": content.get("input", {}),
            })
        elif log["role"] == "tool_result":
            if not messages or messages[-1]["role"] != "user":
                messages.append({"role": "user", "content": []})
            if isinstance(messages[-1]["content"], str):
                messages[-1]["content"] = [{"type": "text", "text": messages[-1]["content"]}]
            content = json.loads(log["content"]) if log["content"] else {}
            messages[-1]["content"].append({
                "type": "tool_result",
                "tool_use_id": content.get("tool_use_id", "unknown"),
                "content": content.get("result", ""),
            })
        elif log["role"] == "system":
            messages.append({"role": "user", "content": log["content"]})

    if not messages:
        return await _build_initial_context(job_id)

    return system, messages


async def run_research_session(job_id: int) -> None:
    """Main session loop. Runs until budget hit, user pause, or Claude end_turn."""
    async with get_async_db() as conn:
        job = await conn.fetchrow("SELECT * FROM research_jobs WHERE id=$1", job_id)
        if not job:
            return

    has_logs = False
    async with get_async_db() as conn:
        count = await conn.fetchval("SELECT COUNT(*) FROM research_logs WHERE research_job_id=$1", job_id)
        has_logs = count > 0

    if has_logs:
        system, messages = await _rebuild_conversation(job_id)
    else:
        system, messages = await _build_initial_context(job_id)

    session_start = time.time()
    async with get_async_db() as conn:
        await conn.execute(
            "UPDATE research_jobs SET session_started_at=to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS') WHERE id=$1",
            job_id,
        )

    model = job["model"] or "claude-sonnet-4-6"
    max_iter = job["max_iterations"]
    max_wall = job["max_wall_clock_seconds"]
    max_plateau = job["no_improvement_plateau"]

    retries = 0

    while True:
        # Budget checks
        async with get_async_db() as conn:
            job = await conn.fetchrow("SELECT * FROM research_jobs WHERE id=$1", job_id)

        if job["status"] != "active":
            return

        if job["current_iteration"] >= max_iter:
            async with get_async_db() as conn:
                await _log(conn, job_id, "system", f"Budget exhausted: {max_iter} iterations reached")
                await conn.execute("UPDATE research_jobs SET status='paused' WHERE id=$1", job_id)
            return

        if time.time() - session_start > max_wall:
            async with get_async_db() as conn:
                await _log(conn, job_id, "system", f"Budget exhausted: {max_wall}s wall-clock reached")
                await conn.execute("UPDATE research_jobs SET status='paused' WHERE id=$1", job_id)
            return

        if job["iterations_since_checkpoint"] >= max_plateau:
            async with get_async_db() as conn:
                await _log(conn, job_id, "system", f"Budget exhausted: {max_plateau} iterations without improvement")
                await conn.execute("UPDATE research_jobs SET status='paused' WHERE id=$1", job_id)
            return

        # Check for user injections
        async with get_async_db() as conn:
            pending = await conn.fetch(
                "SELECT id, content FROM research_messages WHERE research_job_id=$1 AND consumed=FALSE ORDER BY created_at ASC",
                job_id,
            )
            for msg in pending:
                messages.append({"role": "user", "content": msg["content"]})
                await _log(conn, job_id, "user_inject", msg["content"])
                await conn.execute("UPDATE research_messages SET consumed=TRUE WHERE id=$1", msg["id"])

        # SDK turn
        try:
            response = await _sdk_turn(messages, model=model, system=system, tools=TOOL_SCHEMAS)
            retries = 0
        except Exception as exc:
            retries += 1
            if retries >= 3:
                async with get_async_db() as conn:
                    await _log(conn, job_id, "system", f"SDK error after 3 retries: {exc}")
                    await conn.execute("UPDATE research_jobs SET status='paused' WHERE id=$1", job_id)
                return
            import asyncio as _aio
            await _aio.sleep(30)
            continue

        # Log assistant response
        async with get_async_db() as conn:
            for block in response.content:
                if block.type == "text":
                    await _log(conn, job_id, "assistant", block.text, token_count=response.usage.output_tokens)
                elif block.type == "tool_use":
                    await _log(conn, job_id, "tool_call",
                        json.dumps({"tool_use_id": block.id, "input": block.input}),
                        tool_name=block.name)

        # Append assistant message to conversation
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            async with get_async_db() as conn:
                await _log(conn, job_id, "system", f"Claude ended turn: {response.stop_reason}")
                await conn.execute("UPDATE research_jobs SET status='completed' WHERE id=$1", job_id)
            return

        # Execute tool calls
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                result_str = await execute_tool(block.name, block.input, job_id)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result_str,
                })
                async with get_async_db() as conn:
                    await _log(conn, job_id, "tool_result",
                        json.dumps({"tool_use_id": block.id, "result": result_str}),
                        tool_name=block.name)

                # Update iteration counters for propose_params and search
                if block.name in ("propose_params", "search"):
                    is_checkpoint = False
                    if block.name == "search":
                        try:
                            sr = json.loads(result_str)
                            is_checkpoint = sr.get("improved", False)
                        except Exception:
                            pass

                    async with get_async_db() as conn:
                        if is_checkpoint:
                            await conn.execute(
                                "UPDATE research_jobs SET current_iteration=current_iteration+1, iterations_since_checkpoint=0 WHERE id=$1",
                                job_id,
                            )
                        else:
                            await conn.execute(
                                "UPDATE research_jobs SET current_iteration=current_iteration+1, iterations_since_checkpoint=iterations_since_checkpoint+1 WHERE id=$1",
                                job_id,
                            )

                elif block.name == "checkpoint":
                    async with get_async_db() as conn:
                        await conn.execute(
                            "UPDATE research_jobs SET iterations_since_checkpoint=0 WHERE id=$1",
                            job_id,
                        )

        messages.append({"role": "user", "content": tool_results})
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
psql "postgres://tychos:tychos@localhost:5432/tychos_research_redesign_test" -c "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;"
DATABASE_URL=postgres://tychos:tychos@localhost:5432/tychos_research_redesign_test TYCHOS_ADMIN_USER=admin@t.local TYCHOS_ADMIN_PASSWORD=pw PYTHONPATH=tychos_skyfield:tests:. pytest tests/test_researcher_session.py -v
```

- [ ] **Step 5: Commit**

```bash
git add server/researcher/session.py tests/test_researcher_session.py
git commit -m "feat(researcher): session runner with budget enforcement and message injection"
```

---

## Task 4: Manager + crash recovery

**Files:**
- Create: `server/researcher/manager.py`

- [ ] **Step 1: Implement `server/researcher/manager.py`**

```python
"""Researcher task manager — tracks running sessions, handles start/stop/resume."""
import asyncio

from server.db import get_async_db
from server.researcher.session import run_research_session

_tasks: dict[int, asyncio.Task] = {}


def is_running(job_id: int) -> bool:
    task = _tasks.get(job_id)
    return task is not None and not task.done()


async def start(job_id: int) -> bool:
    if is_running(job_id):
        return False
    async with get_async_db() as conn:
        await conn.execute(
            "UPDATE research_jobs SET status='active', current_iteration=0, iterations_since_checkpoint=0 WHERE id=$1",
            job_id,
        )
    task = asyncio.create_task(_run_with_cleanup(job_id))
    _tasks[job_id] = task
    return True


async def resume(job_id: int) -> bool:
    if is_running(job_id):
        return False
    async with get_async_db() as conn:
        await conn.execute("UPDATE research_jobs SET status='active' WHERE id=$1", job_id)
    task = asyncio.create_task(_run_with_cleanup(job_id))
    _tasks[job_id] = task
    return True


async def pause(job_id: int) -> bool:
    async with get_async_db() as conn:
        await conn.execute("UPDATE research_jobs SET status='paused' WHERE id=$1", job_id)
    return True


async def stop(job_id: int) -> None:
    task = _tasks.pop(job_id, None)
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


async def recover_active_jobs() -> int:
    """Called on server startup — respawn tasks for any jobs left as 'active'."""
    async with get_async_db() as conn:
        rows = await conn.fetch("SELECT id FROM research_jobs WHERE status='active'")
    count = 0
    for row in rows:
        if not is_running(row["id"]):
            task = asyncio.create_task(_run_with_cleanup(row["id"]))
            _tasks[row["id"]] = task
            count += 1
    return count


async def _run_with_cleanup(job_id: int) -> None:
    try:
        await run_research_session(job_id)
    except asyncio.CancelledError:
        pass
    except Exception as exc:
        async with get_async_db() as conn:
            await conn.execute(
                "INSERT INTO research_logs (research_job_id, role, content) VALUES ($1,'system',$2)",
                job_id, f"Session crashed: {exc}",
            )
            await conn.execute("UPDATE research_jobs SET status='paused' WHERE id=$1", job_id)
    finally:
        _tasks.pop(job_id, None)
```

- [ ] **Step 2: Commit**

```bash
git add server/researcher/manager.py
git commit -m "feat(researcher): task manager with start/pause/resume/crash-recovery"
```

---

## Task 5: API control endpoints

**Files:**
- Modify: `server/api/research_routes.py`
- Modify: `server/app.py`
- Create: `tests/test_researcher_api.py`

- [ ] **Step 1: Write failing test `tests/test_researcher_api.py`**

```python
import json
import pytest
import pytest_asyncio
import httpx
from unittest.mock import patch, AsyncMock

import server.db as _dbmod
from server.db import init_db, get_db, get_async_db, DATABASE_URL
from server.app import app


@pytest.fixture(autouse=True, scope="module")
def _init():
    import psycopg2
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;")
    conn.close()
    init_db()


@pytest_asyncio.fixture(autouse=True)
async def _reset_async_pool():
    pool = _dbmod._async_pool
    if pool is not None:
        try:
            await pool.close()
        except Exception:
            pass
        _dbmod._async_pool = None
    yield
    pool = _dbmod._async_pool
    if pool is not None:
        try:
            await pool.close()
        except Exception:
            pass
        _dbmod._async_pool = None


async def _login(c):
    await c.post("/api/auth/login", json={"email": "admin@t.local", "password": "pw"})


async def _create_job(c):
    await _login(c)
    r = await c.post("/api/research", json={
        "name": "api-test",
        "param_set_id": 1,
        "dataset_id": 1,
        "view_name": "v_solar_position",
        "allowlist": ["sun.*"],
        "model": "claude-sonnet-4-6",
        "max_iterations": 5,
        "no_improvement_plateau": 3,
    })
    return r.json()


@pytest.mark.asyncio
async def test_create_job_with_budget_fields():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        job = await _create_job(c)
        assert job["model"] == "claude-sonnet-4-6"
        assert job["max_iterations"] == 5
        assert job["no_improvement_plateau"] == 3
        assert job["max_wall_clock_seconds"] == 3600
        assert job["status"] == "pending"


@pytest.mark.asyncio
async def test_start_pause_resume():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        job = await _create_job(c)

        with patch("server.researcher.manager.start", new_callable=AsyncMock, return_value=True) as mock_start:
            r = await c.post(f"/api/research/{job['id']}/start")
            assert r.status_code == 200
            mock_start.assert_called_once_with(job["id"])

        with patch("server.researcher.manager.pause", new_callable=AsyncMock, return_value=True) as mock_pause:
            r = await c.post(f"/api/research/{job['id']}/pause")
            assert r.status_code == 200
            mock_pause.assert_called_once_with(job["id"])

        with patch("server.researcher.manager.resume", new_callable=AsyncMock, return_value=True) as mock_resume:
            r = await c.post(f"/api/research/{job['id']}/resume")
            assert r.status_code == 200
            mock_resume.assert_called_once_with(job["id"])


@pytest.mark.asyncio
async def test_inject_message():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        job = await _create_job(c)
        r = await c.post(f"/api/research/{job['id']}/message", json={"content": "Try sun.speed next"})
        assert r.status_code == 201
        body = r.json()
        assert body["content"] == "Try sun.speed next"
        assert body["consumed"] is False


@pytest.mark.asyncio
async def test_get_logs():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        job = await _create_job(c)
        # Insert a log directly
        async with get_async_db() as conn:
            await conn.execute(
                "INSERT INTO research_logs (research_job_id, role, content) VALUES ($1, 'system', 'test log')",
                job["id"],
            )
        r = await c.get(f"/api/research/{job['id']}/logs")
        assert r.status_code == 200
        logs = r.json()
        assert len(logs) >= 1
        assert logs[0]["role"] == "system"
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
psql "postgres://tychos:tychos@localhost:5432/tychos_research_redesign_test" -c "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;"
DATABASE_URL=postgres://tychos:tychos@localhost:5432/tychos_research_redesign_test TYCHOS_ADMIN_USER=admin@t.local TYCHOS_ADMIN_PASSWORD=pw PYTHONPATH=tychos_skyfield:tests:. pytest tests/test_researcher_api.py -v
```

- [ ] **Step 3: Extend `CreateJobBody` and add control endpoints to `server/api/research_routes.py`**

At the top of the file, add to `CreateJobBody`:
```python
class CreateJobBody(BaseModel):
    name: str
    param_set_id: int
    dataset_id: int
    view_name: str
    allowlist: list[str]
    date_start: str | None = None
    date_end: str | None = None
    model: str = "claude-sonnet-4-6"
    max_iterations: int = 40
    max_wall_clock_seconds: int = 3600
    no_improvement_plateau: int = 6
```

Update `create_research_job` INSERT to include new fields:
```python
job_id = await conn.fetchval(
    "INSERT INTO research_jobs (name, param_set_id, dataset_id, view_name, allowlist, date_start, date_end, "
    "model, max_iterations, max_wall_clock_seconds, no_improvement_plateau, status) "
    "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,'pending') RETURNING id",
    body.name, body.param_set_id, body.dataset_id, body.view_name,
    body.allowlist, body.date_start, body.date_end,
    body.model, body.max_iterations, body.max_wall_clock_seconds, body.no_improvement_plateau,
)
```

Also update `_ALLOWED_STATUSES` to include `"pending"`.

Add new endpoints at the bottom of the file:
```python
import server.researcher.manager as _manager


class InjectMessageBody(BaseModel):
    content: str


@router.post("/{job_id}/start")
async def start_research(job_id: int, request: Request):
    await require_user(request)
    async with get_async_db() as conn:
        job = await conn.fetchrow("SELECT id FROM research_jobs WHERE id=$1", job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Research job not found")
    await _manager.start(job_id)
    return {"ok": True, "job_id": job_id, "status": "active"}


@router.post("/{job_id}/pause")
async def pause_research(job_id: int, request: Request):
    await require_user(request)
    await _manager.pause(job_id)
    return {"ok": True, "job_id": job_id, "status": "paused"}


@router.post("/{job_id}/resume")
async def resume_research(job_id: int, request: Request):
    await require_user(request)
    await _manager.resume(job_id)
    return {"ok": True, "job_id": job_id, "status": "active"}


@router.post("/{job_id}/message", status_code=201)
async def inject_message(job_id: int, body: InjectMessageBody, request: Request):
    await require_user(request)
    async with get_async_db() as conn:
        row = await conn.fetchrow(
            "INSERT INTO research_messages (research_job_id, content) VALUES ($1,$2) RETURNING *",
            job_id, body.content,
        )
    return dict(row)


@router.get("/{job_id}/logs")
async def get_logs(job_id: int, limit: int = 100, offset: int = 0):
    async with get_async_db() as conn:
        rows = await conn.fetch(
            "SELECT * FROM research_logs WHERE research_job_id=$1 ORDER BY created_at ASC, id ASC LIMIT $2 OFFSET $3",
            job_id, limit, offset,
        )
    return [dict(r) for r in rows]
```

- [ ] **Step 4: Update `server/app.py` lifespan for crash recovery**

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    import server.researcher.manager as mgr
    count = await mgr.recover_active_jobs()
    if count:
        print(f"[researcher] Resumed {count} active research job(s)")
    yield
```

- [ ] **Step 5: Run tests — expect PASS**

```bash
psql "postgres://tychos:tychos@localhost:5432/tychos_research_redesign_test" -c "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;"
DATABASE_URL=postgres://tychos:tychos@localhost:5432/tychos_research_redesign_test TYCHOS_ADMIN_USER=admin@t.local TYCHOS_ADMIN_PASSWORD=pw PYTHONPATH=tychos_skyfield:tests:. pytest tests/test_researcher_api.py -v
```

- [ ] **Step 6: Run full suite**

```bash
psql "postgres://tychos:tychos@localhost:5432/tychos_research_redesign_test" -c "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;"
DATABASE_URL=postgres://tychos:tychos@localhost:5432/tychos_research_redesign_test TYCHOS_ADMIN_USER=admin@t.local TYCHOS_ADMIN_PASSWORD=pw PYTHONPATH=tychos_skyfield:tests:. pytest tests/ -v
```

- [ ] **Step 7: Commit**

```bash
git add server/api/research_routes.py server/app.py tests/test_researcher_api.py
git commit -m "feat(researcher): control endpoints (start/pause/resume/message/logs) + crash recovery"
```

---

## Task 6: SSE streaming endpoint

**Files:**
- Modify: `server/api/research_routes.py`

- [ ] **Step 1: Add SSE endpoint**

```python
from sse_starlette.sse import EventSourceResponse
import asyncpg as _asyncpg
import asyncio as _asyncio


@router.get("/{job_id}/logs/stream")
async def stream_logs(job_id: int):
    async def event_generator():
        conn = await _asyncpg.connect(dsn=os.environ.get("DATABASE_URL", ""))
        try:
            await conn.add_listener("research_log_append", lambda *args: None)
            queue: _asyncio.Queue = _asyncio.Queue()

            def _on_notify(conn, pid, channel, payload):
                queue.put_nowait(payload)

            await conn.remove_listener("research_log_append", lambda *args: None)
            await conn.add_listener("research_log_append", _on_notify)

            while True:
                try:
                    payload = await _asyncio.wait_for(queue.get(), timeout=30.0)
                    import json as _j
                    data = _j.loads(payload)
                    if data.get("job_id") == job_id:
                        async with get_async_db() as db:
                            row = await db.fetchrow("SELECT * FROM research_logs WHERE id=$1", data["log_id"])
                        if row:
                            yield {"event": "log", "data": _j.dumps(dict(row))}
                except _asyncio.TimeoutError:
                    yield {"event": "ping", "data": ""}
        finally:
            await conn.close()

    return EventSourceResponse(event_generator())
```

Add `import os` to the top of the file if not present.

- [ ] **Step 2: Commit**

```bash
git add server/api/research_routes.py
git commit -m "feat(researcher): SSE streaming endpoint for research logs"
```

---

## Task 7: Full suite verification + smoke test

**Files:**
- No new files

- [ ] **Step 1: Run full test suite on isolated DB**

```bash
psql "postgres://tychos:tychos@localhost:5432/tychos_research_redesign_test" -c "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;"
DATABASE_URL=postgres://tychos:tychos@localhost:5432/tychos_research_redesign_test TYCHOS_ADMIN_USER=admin@t.local TYCHOS_ADMIN_PASSWORD=pw PYTHONPATH=tychos_skyfield:tests:. pytest tests/ -v
```
All tests must pass.

- [ ] **Step 2: Smoke test with real API key (manual)**

If `ANTHROPIC_API_KEY` is set, run a single-iteration real session:
```bash
psql "postgres://tychos:tychos@localhost:5432/tychos_research_redesign" -c "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;"
DATABASE_URL=postgres://tychos:tychos@localhost:5432/tychos_research_redesign TYCHOS_ADMIN_USER=admin@t.local TYCHOS_ADMIN_PASSWORD=pw ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY PYTHONPATH=tychos_skyfield:tests:. python -c "
import asyncio
from server.db import init_db, get_db, get_async_db
init_db()

# Drain seed runs so worker doesn't block
with get_db() as conn:
    with conn.cursor() as cur:
        cur.execute(\"DELETE FROM runs WHERE status='queued'\")
    conn.commit()

# Start worker in background
from server.worker import start_worker
start_worker()

async def go():
    async with get_async_db() as conn:
        job_id = await conn.fetchval(
            \"INSERT INTO research_jobs (name, param_set_id, dataset_id, view_name, allowlist, status, max_iterations, date_start, date_end) \"
            \"VALUES ('smoke', 1, 1, 'v_solar_position', '{sun.*}', 'active', 2, '1950-01-01', '1952-12-31') RETURNING id\"
        )
    from server.researcher.session import run_research_session
    await run_research_session(job_id)
    async with get_async_db() as conn:
        job = await conn.fetchrow('SELECT status, current_iteration FROM research_jobs WHERE id=\$1', job_id)
        logs = await conn.fetch('SELECT role, tool_name, content FROM research_logs WHERE research_job_id=\$1 ORDER BY id', job_id)
    print(f'Job status: {job[\"status\"]}, iterations: {job[\"current_iteration\"]}')
    print(f'Log entries: {len(logs)}')
    for l in logs[:10]:
        print(f'  {l[\"role\"]:12s} {l[\"tool_name\"] or \"\": <20s} {(l[\"content\"] or \"\")[:80]}')

asyncio.run(go())
"
```

- [ ] **Step 3: Verify server boots with crash recovery**

```bash
DATABASE_URL=postgres://tychos:tychos@localhost:5432/tychos_research_redesign TYCHOS_ADMIN_USER=admin@t.local TYCHOS_ADMIN_PASSWORD=pw ANTHROPIC_API_KEY=test PYTHONPATH=tychos_skyfield:tests:. python -c "from server.app import app; print(len(app.routes), 'routes')"
```

---

## Self-Review Checklist

- **Spec coverage:**
  - `research_logs` table — Task 1 ✓
  - `research_messages` table — Task 1 ✓
  - `research_jobs` new columns (model, budgets, counters) — Task 1 ✓
  - NOTIFY trigger for log append — Task 1 ✓
  - Tool definitions (propose_params, checkpoint, restore, search) — Task 2 ✓
  - Tool execution with detail truncation (top 10 normal, full at decision points) — Task 2 ✓
  - Session runner with SDK loop — Task 3 ✓
  - Budget enforcement (iterations, wall-clock, plateau) — Task 3 ✓
  - User message injection — Task 3 ✓
  - Conversation reconstruction from logs — Task 3 ✓
  - Error retry (3x, 30s backoff) — Task 3 ✓
  - Manager (start/pause/resume) — Task 4 ✓
  - Crash recovery on startup — Task 4 + Task 5 (lifespan) ✓
  - API endpoints (start/pause/resume/message/logs/stream) — Task 5 + Task 6 ✓
  - Extended CreateJobBody with model + budget fields — Task 5 ✓
  - SSE streaming via NOTIFY bridge — Task 6 ✓
  - `anthropic` + `sse-starlette` deps — Task 1 ✓
  - `ANTHROPIC_API_KEY` env var — Task 1 ✓

- **Placeholder scan:** No TBD/TODO found. All code blocks are complete.

- **Type consistency:**
  - `execute_tool(tool_name, tool_input, job_id)` signature matches across tools.py definition, session.py calls, and test mocks ✓
  - `_sdk_turn(messages, model=, system=, tools=)` signature matches session.py definition and test patches ✓
  - `TOOL_SCHEMAS` list used in both session.py and test_researcher_tools.py ✓
  - Manager functions (`start`, `pause`, `resume`, `recover_active_jobs`) match between manager.py and research_routes.py calls ✓
  - `CreateJobBody` field names match migration column names ✓

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-15-researcher-daemon.md`. Two execution options:

**1. Subagent-Driven (recommended)** — Dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

**Which approach?**
