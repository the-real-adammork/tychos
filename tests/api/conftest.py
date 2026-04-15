import pytest
import server.db as _dbmod
from server.db import init_db, get_db


import pytest_asyncio


@pytest_asyncio.fixture(autouse=True)
async def _reset_async_pool():
    """asyncpg pool is tied to an event loop; pytest-asyncio gives each test
    a fresh loop, so close the pool between tests to avoid stale connections."""
    yield
    pool = _dbmod._async_pool
    if pool is not None:
        try:
            await pool.close()
        except Exception:
            pass
        _dbmod._async_pool = None


@pytest.fixture
def seed_run():
    init_db()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM param_versions ORDER BY id LIMIT 1")
            pv_id = cur.fetchone()[0]
            cur.execute("SELECT id FROM datasets ORDER BY id LIMIT 1")
            ds_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO runs (param_version_id, dataset_id, status) VALUES (%s,%s,'done') RETURNING id",
                (pv_id, ds_id),
            )
            run_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO eclipse_results (run_id, julian_day_tt, date, catalog_type, magnitude, detected, threshold_arcmin, sun_delta_ra_arcmin, sun_delta_dec_arcmin, moon_delta_ra_arcmin, moon_delta_dec_arcmin) "
                "VALUES (%s, 2450000.0, '2000-01-01', 'total', 1.0, true, 0.5, 3.0, 4.0, 6.0, 8.0)",
                (run_id,),
            )
            cur.execute(
                "INSERT INTO eclipse_results (run_id, julian_day_tt, date, catalog_type, magnitude, detected, threshold_arcmin, sun_delta_ra_arcmin, sun_delta_dec_arcmin, moon_delta_ra_arcmin, moon_delta_dec_arcmin) "
                "VALUES (%s, 2450001.0, '2001-01-01', 'total', 1.0, true, 0.5, 1.0, 0.0, 3.0, 4.0)",
                (run_id,),
            )
        conn.commit()
    return run_id
