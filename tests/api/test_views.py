import pytest
import httpx
from server.app import app


@pytest.mark.asyncio
async def test_view_returns_objective_and_detail(seed_run):
    run_id = seed_run
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get(f"/api/results/{run_id}/view/v_solar_position")
    assert r.status_code == 200
    data = r.json()
    assert data["n_scored"] == 2
    assert data["detail"][0]["error"] >= data["detail"][1]["error"]
    # First row has (3,4) => sqrt(25)=5; second (1,0) => 1. So objective = (5+1)/2 = 3.0
    assert abs(data["objective"] - 3.0) < 1e-6


@pytest.mark.asyncio
async def test_view_unknown_name_returns_404():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/api/results/1/view/v_nonexistent")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_view_moon_and_combined(seed_run):
    run_id = seed_run
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        moon = (await c.get(f"/api/results/{run_id}/view/v_moon_position")).json()
        combined = (await c.get(f"/api/results/{run_id}/view/v_combined_position")).json()
    # moon: (6,8)=10 and (3,4)=5 -> avg 7.5
    assert abs(moon["objective"] - 7.5) < 1e-6
    # combined: sqrt(9+16+36+64)=sqrt(125), sqrt(1+0+9+16)=sqrt(26) -> avg
    import math
    expected = (math.sqrt(125) + math.sqrt(26)) / 2
    assert abs(combined["objective"] - expected) < 1e-6
