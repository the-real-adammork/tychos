import pytest
import httpx
from server.db import init_db
from server.app import app


@pytest.fixture(autouse=True)
def _init():
    init_db()


@pytest.mark.asyncio
async def test_search_endpoint_runs_and_returns_winner():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        timeout=120.0,
    ) as c:
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
        assert r.status_code == 200, r.text
        out = r.json()
        assert "starting_objective" in out
        assert "best_objective" in out
        assert "n_evals" in out
        assert out["winner_version_id"] is None or out["winner_version_id"] > 0
