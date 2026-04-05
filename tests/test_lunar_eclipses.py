"""
Test Tychos model predictions against the NASA lunar eclipse catalog.

For each eclipse, scans a time window to find when Tychos predicts
minimum Moon-to-antisolar-point separation, and reports whether it
falls below the detection threshold.
"""
import json
import csv
import numpy as np
from pathlib import Path
from tychos_skyfield import baselib as T
from helpers import (
    scan_lunar_eclipse,
    LUNAR_UMBRAL_RADIUS, LUNAR_PENUMBRAL_RADIUS,
    MOON_MEAN_ANGULAR_RADIUS, MINUTE_IN_DAYS,
)


DATA_PATH = Path(__file__).parent / "data" / "lunar_eclipses.json"
RESULTS_PATH = Path(__file__).parent / "data" / "lunar_eclipse_results.csv"


def get_threshold(catalog_type):
    """Get detection threshold based on eclipse type."""
    if catalog_type == "penumbral":
        return LUNAR_PENUMBRAL_RADIUS + MOON_MEAN_ANGULAR_RADIUS
    else:
        return LUNAR_UMBRAL_RADIUS + MOON_MEAN_ANGULAR_RADIUS


def load_eclipses():
    with open(DATA_PATH) as f:
        return json.load(f)


def run_lunar_eclipse_tests():
    eclipses = load_eclipses()
    system = T.TychosSystem()

    results = []
    detected_count = 0
    type_counts = {}
    type_detected = {}

    for i, eclipse in enumerate(eclipses):
        jd = eclipse["julian_day_tt"]
        min_sep, best_jd = scan_lunar_eclipse(system, jd)

        threshold = get_threshold(eclipse["type"])
        detected = min_sep < threshold
        min_sep_arcmin = np.degrees(min_sep) * 60
        timing_offset_min = (best_jd - jd) / MINUTE_IN_DAYS

        etype = eclipse["type"]
        type_counts[etype] = type_counts.get(etype, 0) + 1
        if detected:
            detected_count += 1
            type_detected[etype] = type_detected.get(etype, 0) + 1

        results.append({
            "date": eclipse["date"],
            "catalog_type": etype,
            "magnitude": eclipse["magnitude"],
            "detected": "yes" if detected else "no",
            "min_separation_arcmin": round(min_sep_arcmin, 2),
            "timing_offset_min": round(timing_offset_min, 1),
        })

        status = "DETECTED" if detected else "MISSED"
        print(f"[{i+1}/{len(eclipses)}] {eclipse['date']} {etype:10s} "
              f"sep={min_sep_arcmin:7.2f}' offset={timing_offset_min:+6.1f}min "
              f"{status}")

    # Write results CSV
    with open(RESULTS_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=results[0].keys())
        writer.writeheader()
        writer.writerows(results)

    # Summary
    print("\n=== LUNAR ECLIPSE SUMMARY ===")
    print(f"Total eclipses tested: {len(eclipses)}")
    print(f"Detected: {detected_count} / {len(eclipses)}")
    print()
    for etype in sorted(type_counts.keys()):
        det = type_detected.get(etype, 0)
        tot = type_counts[etype]
        print(f"  {etype:10s}: {det}/{tot}")

    detected_results = [r for r in results if r["detected"] == "yes"]
    if detected_results:
        offsets = [abs(r["timing_offset_min"]) for r in detected_results]
        print(f"\nTiming offset (detected eclipses):")
        print(f"  Mean: {np.mean(offsets):.1f} min")
        print(f"  Max:  {np.max(offsets):.1f} min")

    print(f"\nResults written to: {RESULTS_PATH}")


if __name__ == "__main__":
    run_lunar_eclipse_tests()
