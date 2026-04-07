"""Background worker thread that processes queued eclipse runs."""
import json
import math
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

_POLL_INTERVAL = 5


def _angular_sep_arcmin(ra1, dec1, ra2, dec2):
    """Vincenty angular separation in arcminutes."""
    dra = ra2 - ra1
    num = math.sqrt(
        (math.cos(dec2) * math.sin(dra)) ** 2
        + (math.cos(dec1) * math.sin(dec2) - math.sin(dec1) * math.cos(dec2) * math.cos(dra)) ** 2
    )
    den = math.sin(dec1) * math.sin(dec2) + math.cos(dec1) * math.cos(dec2) * math.cos(dra)
    return math.degrees(math.atan2(num, den)) * 60


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
            print(f"[worker] Unexpected loop error:\n{traceback.format_exc()}")
        time.sleep(_POLL_INTERVAL)


def _process_one() -> None:
    """Pick up the oldest queued run, execute it, and write results."""
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT r.id, r.dataset_id, d.slug AS dataset_slug, pv.params_json
              FROM runs r
              JOIN param_versions pv ON r.param_version_id = pv.id
              JOIN datasets d ON r.dataset_id = d.id
             WHERE r.status = 'queued'
             ORDER BY r.created_at ASC
             LIMIT 1
            """
        ).fetchone()

        if row is None:
            return

        run_id = row["id"]
        dataset_id = row["dataset_id"]
        dataset_slug = row["dataset_slug"]
        params = json.loads(row["params_json"])

    with get_db() as conn:
        conn.execute(
            "UPDATE runs SET status = 'running', started_at = ? WHERE id = ?",
            (_now(), run_id),
        )
        conn.commit()

    try:
        eclipses = load_eclipse_catalog(dataset_id)

        if dataset_slug == "solar_eclipse":
            results = scan_solar_eclipses(params, eclipses)
        elif dataset_slug == "lunar_eclipse":
            results = scan_lunar_eclipses(params, eclipses)
        else:
            raise ValueError(f"Unknown dataset slug: {dataset_slug}")

        detected = sum(1 for r in results if r["detected"])

        # Map dataset slug to predicted_reference test_type
        test_type = "solar" if dataset_slug == "solar_eclipse" else "lunar"

        # Load predicted reference geometry (expected separations)
        with get_db() as conn:
            pred_rows = conn.execute(
                "SELECT julian_day_tt, expected_separation_arcmin FROM predicted_reference WHERE test_type = ?",
                (test_type,),
            ).fetchall()
        pred_by_jd = {row["julian_day_tt"]: row for row in pred_rows}

        # Load JPL reference separations
        with get_db() as conn:
            jpl_rows = conn.execute(
                "SELECT julian_day_tt, separation_arcmin FROM jpl_reference WHERE dataset_id = ?",
                (dataset_id,),
            ).fetchall()
        jpl_by_jd = {row["julian_day_tt"]: row for row in jpl_rows}

        for r in results:
            pred = pred_by_jd.get(r["julian_day_tt"])
            jpl = jpl_by_jd.get(r["julian_day_tt"])

            if pred and r["min_separation_arcmin"] is not None:
                r["tychos_error_arcmin"] = round(
                    abs(r["min_separation_arcmin"] - pred["expected_separation_arcmin"]), 4
                )
            else:
                r["tychos_error_arcmin"] = None

            if pred and jpl:
                r["jpl_error_arcmin"] = round(
                    abs(jpl["separation_arcmin"] - pred["expected_separation_arcmin"]), 4
                )
            else:
                r["jpl_error_arcmin"] = None

            r["moon_error_arcmin"] = None  # deprecated

        CHUNK_SIZE = 50
        insert_sql = """
            INSERT INTO eclipse_results (
                run_id, julian_day_tt, date, catalog_type, magnitude,
                detected, threshold_arcmin, min_separation_arcmin,
                timing_offset_min, best_jd,
                sun_ra_rad, sun_dec_rad, moon_ra_rad, moon_dec_rad,
                moon_error_arcmin, moon_ra_vel, moon_dec_vel,
                tychos_error_arcmin, jpl_error_arcmin
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        rows = [
            (
                run_id,
                r["julian_day_tt"], r["date"], r["catalog_type"], r["magnitude"],
                r["detected"], r["threshold_arcmin"], r["min_separation_arcmin"],
                r["timing_offset_min"], r["best_jd"],
                r["sun_ra_rad"], r["sun_dec_rad"], r["moon_ra_rad"], r["moon_dec_rad"],
                r["moon_error_arcmin"], r.get("moon_ra_vel"), r.get("moon_dec_vel"),
                r["tychos_error_arcmin"], r["jpl_error_arcmin"],
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
