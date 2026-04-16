"""End-to-end research flow test.

Exercises: login -> create job -> create version -> worker processes run ->
view endpoint returns objective -> iteration logged -> checkpoint -> restore.
"""
import asyncio
import json

import httpx
import pytest
import pytest_asyncio

import server.db as _dbmod
from server.app import app
from server.db import init_db, get_db, DATABASE_URL
from server.worker import _process_one


@pytest.fixture(autouse=True, scope="module")
def _init():
    import psycopg2

    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;")
    conn.close()

    init_db()

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM runs WHERE status='queued'")
        conn.commit()


@pytest_asyncio.fixture(autouse=True)
async def _reset_async_pool():
    """asyncpg pool is tied to an event loop; pytest-asyncio gives each test a
    fresh loop, so close any stale pool from prior tests to avoid
    'another operation is in progress' errors when the full suite runs."""
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


@pytest.mark.asyncio
async def test_full_research_flow():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=180.0) as c:
        # 1. Login as admin
        login = await c.post("/api/auth/login", json={"email": "admin@t.local", "password": "pw"})
        assert login.status_code == 200, f"login failed: {login.status_code} {login.text}"

        # 2. Create a research job (restricted date range for speed)
        job_resp = await c.post(
            "/api/research",
            json={
                "name": "e2e",
                "param_set_id": 1,
                "dataset_id": 1,
                "view_name": "v_solar_position",
                "allowlist": ["sun.*"],
                "date_start": "1950-01-01",
                "date_end": "1951-12-31",
            },
        )
        assert job_resp.status_code in (200, 201), f"create job failed: {job_resp.status_code} {job_resp.text}"
        job = job_resp.json()

        # 3. Read latest params
        ps = (await c.get(f"/api/params/{job['param_set_id']}")).json()
        latest_id = ps["versions"][0]["id"]
        base_version = (
            await c.get(f"/api/params/{job['param_set_id']}/versions/{latest_id}")
        ).json()
        base = json.loads(base_version["params_json"])

        # 4. Mutate an allowlisted field and POST a new version
        base["sun"]["start_pos"] = base["sun"]["start_pos"] + 0.01
        created_resp = await c.post(
            f"/api/research/{job['id']}/version",
            json={"params_json": json.dumps(base)},
        )
        assert created_resp.status_code == 201, f"version create failed: {created_resp.status_code} {created_resp.text}"
        created = created_resp.json()
        assert created["run_id"] > 0
        assert created["version_id"] > 0

        # 5. Process the queued run inline (no daemon worker thread to leak).
        processed = await asyncio.to_thread(_process_one)
        assert processed is True, "worker did not pick up the queued run"
        run = (await c.get(f"/api/runs/{created['run_id']}")).json()
        assert run["status"] == "done", f"run did not complete: {run}"

        # 6. GET view endpoint and verify objective is populated
        view = (
            await c.get(f"/api/results/{created['run_id']}/view/v_solar_position")
        ).json()
        assert view["n_scored"] > 0
        assert view["objective"] is not None

        # 7. Log the iteration
        it = await c.post(
            f"/api/research/{job['id']}/iterations",
            json={
                "param_version_id": created["version_id"],
                "run_id": created["run_id"],
                "kind": "iterate",
                "objective": view["objective"],
                "aux_stats": {"n_scored": view["n_scored"]},
            },
        )
        assert it.status_code == 201, f"iteration log failed: {it.status_code} {it.text}"

        # 8. Checkpoint the version
        ckpt = await c.post(
            f"/api/research/{job['id']}/checkpoint/{created['version_id']}"
        )
        assert ckpt.status_code == 200, f"checkpoint failed: {ckpt.status_code} {ckpt.text}"
        assert ckpt.json()["is_checkpoint"] is True

        # 9. Restore: verify new version and new run created
        restored = (
            await c.post(f"/api/research/{job['id']}/restore/{created['version_id']}")
        ).json()
        assert restored["version_id"] > created["version_id"]
        assert restored["run_id"] > created["run_id"]
