"""Background worker thread that processes queued eclipse runs."""
import json
import math
import os
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
            SELECT r.id, r.dataset_id,
                   d.slug AS dataset_slug,
                   d.scan_window_hours AS dataset_scan_window_hours,
                   pv.params_json
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
        scan_window_hours = float(row["dataset_scan_window_hours"])
        params = json.loads(row["params_json"])
        scanner_max_workers_env = os.environ.get("TYCHOS_SCANNER_MAX_WORKERS")
        scanner_max_workers = int(scanner_max_workers_env) if scanner_max_workers_env else None

    with get_db() as conn:
        conn.execute(
            "UPDATE runs SET status = 'running', started_at = ? WHERE id = ?",
            (_now(), run_id),
        )
        conn.commit()

    try:
        eclipses = load_eclipse_catalog(dataset_id)

        # Load JPL reference up front so we can pass best_jd lookup to the scanner,
        # which samples Tychos body positions at JPL's moment of minimum separation.
        with get_db() as conn:
            jpl_rows = conn.execute(
                """
                SELECT julian_day_tt, separation_arcmin, best_jd,
                       sun_ra_rad, sun_dec_rad, moon_ra_rad, moon_dec_rad
                  FROM jpl_reference WHERE dataset_id = ?
                """,
                (dataset_id,),
            ).fetchall()
        jpl_by_jd = {row["julian_day_tt"]: row for row in jpl_rows}
        jpl_best_lookup = {
            jd: row["best_jd"] for jd, row in jpl_by_jd.items() if row["best_jd"] is not None
        }

        if dataset_slug == "solar_eclipse":
            results = scan_solar_eclipses(
                params,
                eclipses,
                half_window_hours=scan_window_hours,
                jpl_best_jd_by_catalog_jd=jpl_best_lookup,
                max_workers=scanner_max_workers,
            )
        elif dataset_slug == "lunar_eclipse":
            results = scan_lunar_eclipses(
                params,
                eclipses,
                half_window_hours=scan_window_hours,
                jpl_best_jd_by_catalog_jd=jpl_best_lookup,
                max_workers=scanner_max_workers,
            )
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

        RAD_TO_ARCMIN = (180.0 / math.pi) * 60.0

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

            if jpl and jpl["best_jd"] is not None:
                r["jpl_timing_offset_min"] = round(
                    (jpl["best_jd"] - r["julian_day_tt"]) * 1440.0, 1
                )
            else:
                r["jpl_timing_offset_min"] = None

            r["moon_error_arcmin"] = None  # deprecated

            # Per-body positional deltas: Tychos Sun/Moon at JPL's best_jd vs JPL's
            # Sun/Moon at the same instant. RA delta is scaled by cos(dec) so that
            # magnitude sqrt(dRA^2 + dDec^2) is a true on-sky angle.
            if (
                jpl
                and r.get("tychos_sun_ra_at_jpl_rad") is not None
                and jpl["sun_ra_rad"] is not None
                and jpl["moon_ra_rad"] is not None
            ):
                cos_s = math.cos(jpl["sun_dec_rad"])
                cos_m = math.cos(jpl["moon_dec_rad"])
                r["sun_delta_ra_arcmin"] = round(
                    (r["tychos_sun_ra_at_jpl_rad"] - jpl["sun_ra_rad"]) * cos_s * RAD_TO_ARCMIN, 4
                )
                r["sun_delta_dec_arcmin"] = round(
                    (r["tychos_sun_dec_at_jpl_rad"] - jpl["sun_dec_rad"]) * RAD_TO_ARCMIN, 4
                )
                r["moon_delta_ra_arcmin"] = round(
                    (r["tychos_moon_ra_at_jpl_rad"] - jpl["moon_ra_rad"]) * cos_m * RAD_TO_ARCMIN, 4
                )
                r["moon_delta_dec_arcmin"] = round(
                    (r["tychos_moon_dec_at_jpl_rad"] - jpl["moon_dec_rad"]) * RAD_TO_ARCMIN, 4
                )
            else:
                r["sun_delta_ra_arcmin"] = None
                r["sun_delta_dec_arcmin"] = None
                r["moon_delta_ra_arcmin"] = None
                r["moon_delta_dec_arcmin"] = None

        CHUNK_SIZE = 50
        insert_sql = """
            INSERT INTO eclipse_results (
                run_id, julian_day_tt, date, catalog_type, magnitude,
                detected, threshold_arcmin, min_separation_arcmin,
                timing_offset_min, best_jd,
                sun_ra_rad, sun_dec_rad, moon_ra_rad, moon_dec_rad,
                moon_error_arcmin, moon_ra_vel, moon_dec_vel,
                tychos_error_arcmin, jpl_error_arcmin, jpl_timing_offset_min,
                sun_delta_ra_arcmin, sun_delta_dec_arcmin,
                moon_delta_ra_arcmin, moon_delta_dec_arcmin
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        rows = [
            (
                run_id,
                r["julian_day_tt"], r["date"], r["catalog_type"], r["magnitude"],
                r["detected"], r["threshold_arcmin"], r["min_separation_arcmin"],
                r["timing_offset_min"], r["best_jd"],
                r["sun_ra_rad"], r["sun_dec_rad"], r["moon_ra_rad"], r["moon_dec_rad"],
                r["moon_error_arcmin"], r.get("moon_ra_vel"), r.get("moon_dec_vel"),
                r["tychos_error_arcmin"], r["jpl_error_arcmin"], r["jpl_timing_offset_min"],
                r["sun_delta_ra_arcmin"], r["sun_delta_dec_arcmin"],
                r["moon_delta_ra_arcmin"], r["moon_delta_dec_arcmin"],
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
