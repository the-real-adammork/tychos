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
