"""Benchmark scan_solar_eclipses on a 20-event subset.

Runs the scanner three times (warm-up + 2 timed) for each of:
  - serial (max_workers=1)
  - parallel (max_workers=default)

Prints wall-clock numbers and the speedup ratio. Useful for verifying
the perf claims in spec/plan and as a regression check after
follow-up speed PRs.

Usage:
    python scripts/benchmark_scanner.py
"""
import json
import time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "tests"))
sys.path.insert(0, str(Path(__file__).parent.parent / "tychos_skyfield"))

from server.services.scanner import scan_solar_eclipses

REPO_ROOT = Path(__file__).parent.parent
PARAMS_PATH = REPO_ROOT / "params" / "v1-original" / "v1.json"
CATALOG_PATH = REPO_ROOT / "tests" / "data" / "solar_eclipses.json"
SUBSET_SIZE = 20
HALF_WINDOW = 6.0


def _time_one(label, fn):
    # Warm up (especially important for the parallel path so the pool
    # spawn cost doesn't dominate the first measurement).
    fn()
    t1 = time.perf_counter()
    fn()
    t2 = time.perf_counter()
    fn()
    t3 = time.perf_counter()
    elapsed = ((t2 - t1) + (t3 - t2)) / 2
    print(f"  {label:30s} {elapsed:6.2f} s")
    return elapsed


def main():
    params = json.load(open(PARAMS_PATH))["params"]
    catalog = json.load(open(CATALOG_PATH))[:SUBSET_SIZE]
    print(f"Benchmarking scan_solar_eclipses on {len(catalog)} eclipses, "
          f"half_window_hours={HALF_WINDOW}")
    print()

    serial_time = _time_one(
        "serial (max_workers=1)",
        lambda: scan_solar_eclipses(
            params, catalog, half_window_hours=HALF_WINDOW, max_workers=1
        ),
    )

    parallel_time = _time_one(
        "parallel (default workers)",
        lambda: scan_solar_eclipses(
            params, catalog, half_window_hours=HALF_WINDOW
        ),
    )

    print()
    print(f"Speedup: {serial_time / parallel_time:.2f}x")
    print(f"Documented baseline (pre-refactor): 16.6 s")
    print(f"Serial vs baseline: {16.6 / serial_time:.2f}x faster")
    print(f"Parallel vs baseline: {16.6 / parallel_time:.2f}x faster")


if __name__ == "__main__":
    main()
