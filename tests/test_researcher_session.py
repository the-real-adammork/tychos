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
                "VALUES (%s,%s,%s,%s,%s,'active',3,3600,10,%s,%s) RETURNING id",
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

    # Override plateau for this test
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE research_jobs SET no_improvement_plateau=2 WHERE id=%s", (job_id,))
        conn.commit()

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
