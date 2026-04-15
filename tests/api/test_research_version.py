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
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
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
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
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
