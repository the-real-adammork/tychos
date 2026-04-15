"""Background worker that processes queued eclipse runs (Postgres)."""
import json
import math
import os
import select
import time
import threading
import traceback
from datetime import datetime, timezone

import psycopg2
import psycopg2.extensions

from server.db import get_db, DATABASE_URL
from server.services.scanner import (
    load_eclipse_catalog,
    scan_solar_eclipses,
    scan_lunar_eclipses,
)

_POLL_INTERVAL = 5.0


def start_worker() -> threading.Thread:
    t = threading.Thread(target=_worker_loop, daemon=True, name="eclipse-worker")
    t.start()
    return t


def _worker_loop() -> None:
    listen_conn = psycopg2.connect(DATABASE_URL)
    listen_conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
    with listen_conn.cursor() as cur:
        cur.execute("LISTEN run_queued")

    while True:
        try:
            # Drain anything queued before we started listening.
            _process_all_queued()

            # Wait for the next NOTIFY or a poll-interval timeout.
            if select.select([listen_conn], [], [], _POLL_INTERVAL) == ([], [], []):
                pass  # timeout — fall through to poll
            listen_conn.poll()
            while listen_conn.notifies:
                listen_conn.notifies.pop(0)  # drain; _process_all_queued handles the row
        except Exception:
            print(f"[worker] Unexpected loop error:\n{traceback.format_exc()}")
            time.sleep(1.0)


def _process_all_queued() -> None:
    while _process_one():
        pass


def _process_one() -> bool:
    """Pick up the oldest queued run, execute it. Returns True if one was processed."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT r.id, r.dataset_id, r.date_start, r.date_end,
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
            )
            row = cur.fetchone()
        if row is None:
            return False
        run_id = row["id"]
        dataset_id = row["dataset_id"]
        dataset_slug = row["dataset_slug"]
        date_start = row["date_start"]
        date_end = row["date_end"]
        scan_window_hours = float(row["dataset_scan_window_hours"])
        params = json.loads(row["params_json"])
        scanner_max_workers_env = os.environ.get("TYCHOS_SCANNER_MAX_WORKERS")
        scanner_max_workers = int(scanner_max_workers_env) if scanner_max_workers_env else None

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE runs SET status='running', started_at=%s WHERE id=%s",
                (_now(), run_id),
            )
        conn.commit()

    try:
        eclipses = load_eclipse_catalog(dataset_id)
        if date_start and date_end:
            eclipses = [e for e in eclipses if date_start <= e["date"] <= date_end]

        # --- unchanged scanner + enrichment block ---
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT julian_day_tt, separation_arcmin, best_jd, "
                    "sun_ra_rad, sun_dec_rad, moon_ra_rad, moon_dec_rad "
                    "FROM jpl_reference WHERE dataset_id=%s",
                    (dataset_id,),
                )
                jpl_rows = cur.fetchall()
        jpl_by_jd = {row["julian_day_tt"]: row for row in jpl_rows}
        jpl_best_lookup = {jd: row["best_jd"] for jd, row in jpl_by_jd.items() if row["best_jd"] is not None}

        if dataset_slug == "solar_eclipse":
            results = scan_solar_eclipses(params, eclipses, half_window_hours=scan_window_hours, jpl_best_jd_by_catalog_jd=jpl_best_lookup, max_workers=scanner_max_workers)
        elif dataset_slug == "lunar_eclipse":
            results = scan_lunar_eclipses(params, eclipses, half_window_hours=scan_window_hours, jpl_best_jd_by_catalog_jd=jpl_best_lookup, max_workers=scanner_max_workers)
        else:
            raise ValueError(f"Unknown dataset slug: {dataset_slug}")

        detected = sum(1 for r in results if r["detected"])
        test_type = "solar" if dataset_slug == "solar_eclipse" else "lunar"

        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT julian_day_tt, expected_separation_arcmin FROM predicted_reference WHERE test_type=%s", (test_type,))
                pred_rows = cur.fetchall()
        pred_by_jd = {row["julian_day_tt"]: row for row in pred_rows}

        RAD_TO_ARCMIN = (180.0 / math.pi) * 60.0

        for r in results:
            pred = pred_by_jd.get(r["julian_day_tt"])
            jpl = jpl_by_jd.get(r["julian_day_tt"])
            r["tychos_error_arcmin"] = round(abs(r["min_separation_arcmin"] - pred["expected_separation_arcmin"]), 4) if pred and r["min_separation_arcmin"] is not None else None
            r["jpl_error_arcmin"] = round(abs(jpl["separation_arcmin"] - pred["expected_separation_arcmin"]), 4) if pred and jpl else None
            r["jpl_timing_offset_min"] = round((jpl["best_jd"] - r["julian_day_tt"]) * 1440.0, 1) if jpl and jpl["best_jd"] is not None else None
            r["moon_error_arcmin"] = None
            if jpl and r.get("tychos_sun_ra_at_jpl_rad") is not None and jpl["sun_ra_rad"] is not None and jpl["moon_ra_rad"] is not None:
                cos_s = math.cos(jpl["sun_dec_rad"])
                cos_m = math.cos(jpl["moon_dec_rad"])
                r["sun_delta_ra_arcmin"] = round((r["tychos_sun_ra_at_jpl_rad"] - jpl["sun_ra_rad"]) * cos_s * RAD_TO_ARCMIN, 4)
                r["sun_delta_dec_arcmin"] = round((r["tychos_sun_dec_at_jpl_rad"] - jpl["sun_dec_rad"]) * RAD_TO_ARCMIN, 4)
                r["moon_delta_ra_arcmin"] = round((r["tychos_moon_ra_at_jpl_rad"] - jpl["moon_ra_rad"]) * cos_m * RAD_TO_ARCMIN, 4)
                r["moon_delta_dec_arcmin"] = round((r["tychos_moon_dec_at_jpl_rad"] - jpl["moon_dec_rad"]) * RAD_TO_ARCMIN, 4)
            else:
                r["sun_delta_ra_arcmin"] = r["sun_delta_dec_arcmin"] = r["moon_delta_ra_arcmin"] = r["moon_delta_dec_arcmin"] = None

        insert_sql = """
            INSERT INTO eclipse_results (
                run_id, julian_day_tt, date, catalog_type, magnitude,
                detected, threshold_arcmin, min_separation_arcmin,
                timing_offset_min, best_jd,
                sun_ra_rad, sun_dec_rad, moon_ra_rad, moon_dec_rad,
                moon_error_arcmin, moon_ra_vel, moon_dec_vel,
                tychos_error_arcmin, jpl_error_arcmin, jpl_timing_offset_min,
                sun_delta_ra_arcmin, sun_delta_dec_arcmin,
                moon_delta_ra_arcmin, moon_delta_dec_arcmin,
                tychos_sun_ra_at_jpl_rad, tychos_sun_dec_at_jpl_rad,
                tychos_moon_ra_at_jpl_rad, tychos_moon_dec_at_jpl_rad
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """
        rows = [
            (
                run_id, r["julian_day_tt"], r["date"], r["catalog_type"], r["magnitude"],
                r["detected"], r["threshold_arcmin"], r["min_separation_arcmin"],
                r["timing_offset_min"], r["best_jd"],
                r["sun_ra_rad"], r["sun_dec_rad"], r["moon_ra_rad"], r["moon_dec_rad"],
                r["moon_error_arcmin"], r.get("moon_ra_vel"), r.get("moon_dec_vel"),
                r["tychos_error_arcmin"], r["jpl_error_arcmin"], r["jpl_timing_offset_min"],
                r["sun_delta_ra_arcmin"], r["sun_delta_dec_arcmin"],
                r["moon_delta_ra_arcmin"], r["moon_delta_dec_arcmin"],
                r.get("tychos_sun_ra_at_jpl_rad"), r.get("tychos_sun_dec_at_jpl_rad"),
                r.get("tychos_moon_ra_at_jpl_rad"), r.get("tychos_moon_dec_at_jpl_rad"),
            )
            for r in results
        ]
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.executemany(insert_sql, rows)
            conn.commit()

        sun_mags, moon_mags, timing_abs = [], [], []
        for r in results:
            if r.get("sun_delta_ra_arcmin") is not None and r.get("sun_delta_dec_arcmin") is not None:
                sun_mags.append(math.sqrt(r["sun_delta_ra_arcmin"]**2 + r["sun_delta_dec_arcmin"]**2))
            if r.get("moon_delta_ra_arcmin") is not None and r.get("moon_delta_dec_arcmin") is not None:
                moon_mags.append(math.sqrt(r["moon_delta_ra_arcmin"]**2 + r["moon_delta_dec_arcmin"]**2))
            if r.get("timing_offset_min") is not None:
                timing_abs.append(abs(r["timing_offset_min"]))

        mean_sun_diff = round(sum(sun_mags)/len(sun_mags), 4) if sun_mags else None
        mean_moon_diff = round(sum(moon_mags)/len(moon_mags), 4) if moon_mags else None
        mean_timing_offset = round(sum(timing_abs)/len(timing_abs), 4) if timing_abs else None

        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE runs SET status='done', completed_at=%s, total_eclipses=%s, detected=%s, "
                    "mean_sun_diff=%s, mean_moon_diff=%s, mean_timing_offset=%s WHERE id=%s",
                    (_now(), len(results), detected, mean_sun_diff, mean_moon_diff, mean_timing_offset, run_id),
                )
            conn.commit()

        print(f"[worker] Run {run_id} complete: {detected}/{len(results)}")
        return True

    except Exception as exc:
        error_text = traceback.format_exc()[:2000]
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE runs SET status='failed', error=%s, completed_at=%s WHERE id=%s",
                    (error_text, _now(), run_id),
                )
            conn.commit()
        print(f"[worker] Run {run_id} failed: {exc}")
        return True


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    from server.db import init_db
    init_db()
    print("[worker] Starting standalone worker process")
    _worker_loop()
