import os
import asyncio
import pytest

from server.db import init_db, _run_migrations, get_db, get_async_db, DATABASE_URL


def test_database_url_configured():
    assert DATABASE_URL, "DATABASE_URL env var must be set for the test DB"


def test_run_migrations_creates_tables_and_views():
    _run_migrations()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public.users')")
            assert cur.fetchone()[0] == "users"
            cur.execute("SELECT to_regclass('public.research_jobs')")
            assert cur.fetchone()[0] == "research_jobs"
            cur.execute("SELECT to_regclass('public.v_solar_position')")
            assert cur.fetchone()[0] == "v_solar_position"


@pytest.mark.xfail(reason='seed still sqlite-flavored; resolved in task 7', strict=False)
def test_init_db_creates_tables_and_views():
    init_db()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public.users')")
            assert cur.fetchone()[0] == "users"


def test_async_db_roundtrip():
    async def go():
        async with get_async_db() as conn:
            row = await conn.fetchrow("SELECT 1 AS n")
            assert row["n"] == 1
    asyncio.run(go())
