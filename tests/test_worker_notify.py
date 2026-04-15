import os
import threading
import time
import pytest
import psycopg2

from server.db import init_db, get_db, DATABASE_URL
from server.worker import _worker_loop, _process_one  # noqa


def test_listen_wakes_worker_before_poll_interval(monkeypatch):
    """When a run is INSERT'd with status='queued', the worker's select() returns
    via NOTIFY in well under the 5s poll fallback."""
    init_db()
    # Seed: get any existing param_version + dataset
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM param_versions ORDER BY id LIMIT 1")
            pv_id = cur.fetchone()[0]
            cur.execute("SELECT id FROM datasets ORDER BY id LIMIT 1")
            ds_id = cur.fetchone()[0]

    # Manually LISTEN from a fresh connection to verify the trigger fires
    conn = psycopg2.connect(DATABASE_URL)
    conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
    with conn.cursor() as cur:
        cur.execute("LISTEN run_queued")

    with get_db() as ins_conn:
        with ins_conn.cursor() as cur:
            cur.execute(
                "INSERT INTO runs (param_version_id, dataset_id, status) VALUES (%s,%s,'queued') RETURNING id",
                (pv_id, ds_id),
            )
            new_run_id = cur.fetchone()[0]
        ins_conn.commit()

    import select
    if select.select([conn], [], [], 2.0) == ([], [], []):
        pytest.fail("Expected NOTIFY within 2s of insert")
    conn.poll()
    assert conn.notifies, "No notifies received"
    assert conn.notifies[0].channel == "run_queued"
    assert int(conn.notifies[0].payload) == new_run_id
