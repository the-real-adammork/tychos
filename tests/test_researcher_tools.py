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
