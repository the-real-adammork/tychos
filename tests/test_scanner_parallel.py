"""Fast smoke test for the scanner's parallel execution path.

Verifies that scan_solar_eclipses and scan_lunar_eclipses produce
correct row counts and field shapes when forced through the process
pool with max_workers=2 and parallel_threshold=1. Does NOT compare
against goldens — that's test_scanner_golden.py's job. This is just
a wiring check that runs in the default fast suite.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "tychos_skyfield"))
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from server.services.scanner import scan_solar_eclipses, scan_lunar_eclipses

_PARAMS_PATH = Path(__file__).parent.parent / "params" / "v1-original" / "v1.json"

_EXPECTED_KEYS = {
    "julian_day_tt",
    "date",
    "catalog_type",
    "magnitude",
    "detected",
    "threshold_arcmin",
    "min_separation_arcmin",
    "timing_offset_min",
    "best_jd",
    "sun_ra_rad",
    "sun_dec_rad",
    "moon_ra_rad",
    "moon_dec_rad",
    "moon_ra_vel",
    "moon_dec_vel",
}


@pytest.fixture(scope="module")
def params():
    with open(_PARAMS_PATH) as f:
        return json.load(f)["params"]


# Two known historical eclipses, enough to exceed the test's
# parallel_threshold=1 setting and force a parallel dispatch.
_SOLAR_PAIR = [
    {"julian_day_tt": 2457987.268519, "date": "2017-08-21T18:26:40", "type": "total", "magnitude": 1.0306},
    {"julian_day_tt": 2451748.252257, "date": "1999-08-11T11:03:00", "type": "total", "magnitude": 1.0286},
]

_LUNAR_PAIR = [
    {"julian_day_tt": 2458150.063194, "date": "2018-01-31T13:31:00", "type": "total", "magnitude": 2.2941},
    {"julian_day_tt": 2456935.232639, "date": "2014-10-08T10:55:00", "type": "total", "magnitude": 2.1469},
]


def test_solar_parallel_path_returns_expected_rows(params):
    """Force the parallel dispatcher with threshold=1, max_workers=2."""
    rows = scan_solar_eclipses(
        params,
        _SOLAR_PAIR,
        half_window_hours=6.0,
        max_workers=2,
        parallel_threshold=1,
    )
    assert len(rows) == 2
    for row in rows:
        assert set(row.keys()) == _EXPECTED_KEYS
    # Order is preserved (executor.map preserves input order)
    assert rows[0]["julian_day_tt"] == _SOLAR_PAIR[0]["julian_day_tt"]
    assert rows[1]["julian_day_tt"] == _SOLAR_PAIR[1]["julian_day_tt"]


def test_lunar_parallel_path_returns_expected_rows(params):
    """Force the parallel dispatcher with threshold=1, max_workers=2."""
    rows = scan_lunar_eclipses(
        params,
        _LUNAR_PAIR,
        half_window_hours=6.0,
        max_workers=2,
        parallel_threshold=1,
    )
    assert len(rows) == 2
    for row in rows:
        assert set(row.keys()) == _EXPECTED_KEYS
    assert rows[0]["julian_day_tt"] == _LUNAR_PAIR[0]["julian_day_tt"]
    assert rows[1]["julian_day_tt"] == _LUNAR_PAIR[1]["julian_day_tt"]


def test_serial_and_parallel_produce_identical_output(params):
    """Run the same input through serial (max_workers=1) and parallel
    (max_workers=2, threshold=1) paths and assert byte-identical rows.

    This is the strongest local guarantee that parallelism preserves
    semantics; the goldens are the catalog-scale version of this check.
    """
    serial = scan_solar_eclipses(
        params, _SOLAR_PAIR, half_window_hours=6.0, max_workers=1
    )
    parallel = scan_solar_eclipses(
        params,
        _SOLAR_PAIR,
        half_window_hours=6.0,
        max_workers=2,
        parallel_threshold=1,
    )
    assert serial == parallel
