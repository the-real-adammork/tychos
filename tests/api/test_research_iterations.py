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
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
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
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
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
