#!/usr/bin/env python3
"""
Run Tychos eclipse prediction tests against all parameter sets.

Usage:
    python tests/run_eclipses.py                     # all param sets
    python tests/run_eclipses.py params/v1-original.json  # specific set
    python tests/run_eclipses.py --force             # re-run even if exists
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

# Ensure imports work
sys.path.insert(0, str(Path(__file__).parent.parent / "tychos_skyfield"))
sys.path.insert(0, str(Path(__file__).parent))

from tychos_skyfield import baselib as T
from helpers import (
    scan_min_separation, scan_lunar_eclipse, lunar_threshold,
    SOLAR_DETECTION_THRESHOLD, MINUTE_IN_DAYS,
)
from db import (
    init_db, sync_param_sets, run_exists, insert_run,
    get_param_set, canonical_md5,
)

DATA_DIR = Path(__file__).parent / "data"


def load_eclipses(test_type):
    path = DATA_DIR / f"{test_type}_eclipses.json"
    with open(path) as f:
        return json.load(f)


def run_solar(system, eclipses):
    """Run solar eclipse scan. Returns (detected_count, eclipse_rows)."""
    rows = []
    detected_count = 0
    threshold_arcmin = np.degrees(SOLAR_DETECTION_THRESHOLD) * 60

    for i, ecl in enumerate(eclipses):
        jd = ecl["julian_day_tt"]
        min_sep, best_jd, s_ra, s_dec, m_ra, m_dec = scan_min_separation(system, jd)

        det = min_sep < SOLAR_DETECTION_THRESHOLD
        if det:
            detected_count += 1

        rows.append({
            "julian_day_tt": jd,
            "date": ecl["date"],
            "catalog_type": ecl["type"],
            "magnitude": ecl["magnitude"],
            "detected": 1 if det else 0,
            "threshold_arcmin": round(threshold_arcmin, 4),
            "min_separation_arcmin": round(np.degrees(min_sep) * 60, 2),
            "timing_offset_min": round((best_jd - jd) / MINUTE_IN_DAYS, 1),
            "best_jd": best_jd,
            "sun_ra_rad": float(s_ra),
            "sun_dec_rad": float(s_dec),
            "moon_ra_rad": float(m_ra),
            "moon_dec_rad": float(m_dec),
        })

        status = "DETECTED" if det else "MISSED"
        print(f"  [{i+1}/{len(eclipses)}] {ecl['date']} {ecl['type']:8s} "
              f"sep={rows[-1]['min_separation_arcmin']:7.2f}' "
              f"offset={rows[-1]['timing_offset_min']:+6.1f}min {status}")

    return detected_count, rows


def run_lunar(system, eclipses):
    """Run lunar eclipse scan. Returns (detected_count, eclipse_rows)."""
    rows = []
    detected_count = 0

    for i, ecl in enumerate(eclipses):
        jd = ecl["julian_day_tt"]
        min_sep, best_jd, s_ra, s_dec, m_ra, m_dec = scan_lunar_eclipse(system, jd)

        threshold = lunar_threshold(ecl["type"])
        threshold_arcmin = np.degrees(threshold) * 60
        det = min_sep < threshold
        if det:
            detected_count += 1

        rows.append({
            "julian_day_tt": jd,
            "date": ecl["date"],
            "catalog_type": ecl["type"],
            "magnitude": ecl["magnitude"],
            "detected": 1 if det else 0,
            "threshold_arcmin": round(threshold_arcmin, 4),
            "min_separation_arcmin": round(np.degrees(min_sep) * 60, 2),
            "timing_offset_min": round((best_jd - jd) / MINUTE_IN_DAYS, 1),
            "best_jd": best_jd,
            "sun_ra_rad": float(s_ra),
            "sun_dec_rad": float(s_dec),
            "moon_ra_rad": float(m_ra),
            "moon_dec_rad": float(m_dec),
        })

        status = "DETECTED" if det else "MISSED"
        print(f"  [{i+1}/{len(eclipses)}] {ecl['date']} {ecl['type']:10s} "
              f"sep={rows[-1]['min_separation_arcmin']:7.2f}' "
              f"offset={rows[-1]['timing_offset_min']:+6.1f}min {status}")

    return detected_count, rows


def print_summary(test_type, total, detected, rows):
    """Print detection summary."""
    print(f"\n=== {test_type.upper()} SUMMARY ===")
    print(f"Total: {total}, Detected: {detected}/{total}")

    type_counts = {}
    type_detected = {}
    for r in rows:
        t = r["catalog_type"]
        type_counts[t] = type_counts.get(t, 0) + 1
        if r["detected"]:
            type_detected[t] = type_detected.get(t, 0) + 1

    for t in sorted(type_counts):
        d = type_detected.get(t, 0)
        print(f"  {t:10s}: {d}/{type_counts[t]}")

    det_rows = [r for r in rows if r["detected"]]
    if det_rows:
        offsets = [abs(r["timing_offset_min"]) for r in det_rows]
        print(f"  Timing offset (detected): mean={np.mean(offsets):.1f}min, max={np.max(offsets):.1f}min")


def run_for_param_set(conn, param_name, params_dict, params_md5, param_set_id, force):
    """Run solar and lunar tests for one parameter set."""
    for test_type in ("solar", "lunar"):
        if not force and run_exists(conn, params_md5, test_type):
            print(f"  [{param_name}/{test_type}] already exists, skipping (use --force to re-run)")
            continue

        print(f"\n--- {param_name} / {test_type} ---")
        eclipses = load_eclipses(test_type)
        system = T.TychosSystem(params=params_dict)

        if test_type == "solar":
            detected, rows = run_solar(system, eclipses)
        else:
            detected, rows = run_lunar(system, eclipses)

        insert_run(conn, param_set_id, param_name, test_type,
                   len(eclipses), detected, rows)
        print_summary(test_type, len(eclipses), detected, rows)


def main():
    parser = argparse.ArgumentParser(description="Run Tychos eclipse prediction tests")
    parser.add_argument("params_file", nargs="?", help="Specific params file to test")
    parser.add_argument("--force", action="store_true", help="Re-run even if results exist")
    args = parser.parse_args()

    conn = init_db()
    sync_param_sets(conn)

    if args.params_file:
        path = Path(args.params_file)
        name = path.stem
        ps = get_param_set(conn, name)
        if not ps:
            print(f"ERROR: param set '{name}' not found in database. "
                  f"Make sure {path} exists in params/")
            sys.exit(1)
        param_set_id, _, params_md5, params_json = ps
        params_dict = json.loads(params_json)
        run_for_param_set(conn, name, params_dict, params_md5, param_set_id, args.force)
    else:
        # Run all param sets
        params_dir = Path(__file__).parent.parent / "params"
        for path in sorted(params_dir.glob("*.json")):
            name = path.stem
            ps = get_param_set(conn, name)
            if not ps:
                continue
            param_set_id, _, params_md5, params_json = ps
            params_dict = json.loads(params_json)
            run_for_param_set(conn, name, params_dict, params_md5, param_set_id, args.force)

    # Final summary across all runs
    print("\n=== ALL RUNS ===")
    cursor = conn.execute(
        "SELECT params_name, test_type, total_eclipses, detected, "
        "ROUND(100.0 * detected / total_eclipses, 1) AS pct "
        "FROM runs ORDER BY params_name, test_type"
    )
    for row in cursor:
        print(f"  {row[0]:20s} {row[1]:6s}  {row[3]}/{row[2]} ({row[4]}%)")

    conn.close()


if __name__ == "__main__":
    main()
