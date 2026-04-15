import pytest
import httpx
from server.db import init_db
from server.app import app


@pytest.fixture(autouse=True)
def _init():
    init_db()


async def _login(c):
    r = await c.post(
        "/api/auth/login",
        json={"email": "admin@t.local", "password": "pw"},
    )
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_create_and_get_research_job():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
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
        assert r.status_code == 201, r.text
        job = r.json()
        assert job["id"] > 0
        assert job["status"] == "active"
        assert job["instructions"]  # populated by template

        r2 = await c.get(f"/api/research/{job['id']}")
        assert r2.status_code == 200
        assert r2.json()["name"] == "solar-sim-test"


@pytest.mark.asyncio
async def test_list_research_jobs():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/api/research")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_patch_research_job_status():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        await _login(c)
        created = (await c.post("/api/research", json={
            "name": "paused-job", "param_set_id": 1, "dataset_id": 1,
            "view_name": "v_solar_position", "allowlist": ["sun.*"],
        })).json()
        r = await c.patch(f"/api/research/{created['id']}", json={"status": "paused"})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "paused"


@pytest.mark.asyncio
async def test_view_name_validated_on_create():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        await _login(c)
        r = await c.post("/api/research", json={
            "name": "bad", "param_set_id": 1, "dataset_id": 1,
            "view_name": "v_bogus", "allowlist": ["sun.*"],
        })
        assert r.status_code == 422
