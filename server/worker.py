"""Background worker thread that processes queued eclipse runs."""
import json
import time
import threading
import traceback
from datetime import datetime, timezone

from server.db import get_db
from server.services.scanner import (
    load_eclipse_catalog,
    scan_solar_eclipses,
    scan_lunar_eclipses,
)

_POLL_INTERVAL = 5  # seconds between polls when idle


def start_worker() -> threading.Thread:
    """Start a daemon thread running the worker loop. Returns the thread."""
    t = threading.Thread(target=_worker_loop, daemon=True, name="eclipse-worker")
    t.start()
    return t


def _worker_loop() -> None:
    """Infinite loop: process one queued run, then sleep."""
    while True:
        try:
            _process_one()
        except Exception:
            # Unhandled error in the loop itself — log and keep running.
            print(f"[worker] Unexpected loop error:\n{traceback.format_exc()}")
        time.sleep(_POLL_INTERVAL)


def _process_one() -> None:
    """Pick up the oldest queued run, execute it, and write results."""
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT r.id, r.test_type, p.params_json
              FROM runs r
              JOIN param_sets p ON r.param_set_id = p.id
             WHERE r.status = 'queued'
             ORDER BY r.created_at ASC
             LIMIT 1
            """
        ).fetchone()

        if row is None:
            return

        run_id = row["id"]
        test_type = row["test_type"]
        params = json.loads(row["params_json"])

    # Mark as running (separate connection to commit immediately)
    with get_db() as conn:
        conn.execute(
            "UPDATE runs SET status = 'running', started_at = ? WHERE id = ?",
            (_now(), run_id),
        )
        conn.commit()

    try:
        eclipses = load_eclipse_catalog(test_type)

        if test_type == "solar":
            results = scan_solar_eclipses(params, eclipses)
        else:
            results = scan_lunar_eclipses(params, eclipses)

        detected = sum(1 for r in results if r["detected"])

        # Write results in small chunks to avoid holding the write lock
        CHUNK_SIZE = 50
        insert_sql = """
            INSERT INTO eclipse_results (
                run_id, julian_day_tt, date, catalog_type, magnitude,
                detected, threshold_arcmin, min_separation_arcmin,
                timing_offset_min, best_jd,
                sun_ra_rad, sun_dec_rad, moon_ra_rad, moon_dec_rad
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        rows = [
            (
                run_id,
                r["julian_day_tt"], r["date"], r["catalog_type"], r["magnitude"],
                r["detected"], r["threshold_arcmin"], r["min_separation_arcmin"],
                r["timing_offset_min"], r["best_jd"],
                r["sun_ra_rad"], r["sun_dec_rad"], r["moon_ra_rad"], r["moon_dec_rad"],
            )
            for r in results
        ]
        for i in range(0, len(rows), CHUNK_SIZE):
            chunk = rows[i : i + CHUNK_SIZE]
            with get_db() as conn:
                conn.executemany(insert_sql, chunk)
                conn.commit()

        with get_db() as conn:
            conn.execute(
                """
                UPDATE runs
                   SET status = 'done',
                       completed_at = ?,
                       total_eclipses = ?,
                       detected = ?
                 WHERE id = ?
                """,
                (_now(), len(results), detected, run_id),
            )
            conn.commit()

        print(f"[worker] Run {run_id} complete: {detected}/{len(results)}")

    except Exception as exc:
        error_text = traceback.format_exc()[:2000]
        with get_db() as conn:
            conn.execute(
                """
                UPDATE runs
                   SET status = 'failed',
                       error = ?,
                       completed_at = ?
                 WHERE id = ?
                """,
                (error_text, _now(), run_id),
            )
            conn.commit()
        print(f"[worker] Run {run_id} failed: {exc}")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    from server.db import init_db
    init_db()
    print("[worker] Starting standalone worker process")
    _worker_loop()
