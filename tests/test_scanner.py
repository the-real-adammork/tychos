"""
Tests for server/services/scanner.py
"""
import json
import sys
from pathlib import Path

import pytest

# Allow imports of tychos_skyfield and helpers
sys.path.insert(0, str(Path(__file__).parent.parent / "tychos_skyfield"))
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from server.services.scanner import scan_solar_eclipses, scan_lunar_eclipses

# Param sets are now versioned directories: params/<name>/v<N>.json with the
# raw orbital parameters under a `params` key.
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
        version = json.load(f)
    # Versioned param files wrap the orbital parameters under a `params` key.
    return version["params"]


class TestSolarScanner:
    # 2017-08-21 total solar eclipse — JD 2457987.268519, magnitude 1.0306
    _ECLIPSE_2017 = {
        "julian_day_tt": 2457987.268519,
        "date": "2017-08-21T18:26:40",
        "type": "total",
        "magnitude": 1.0306,
    }

    def test_detects_2017_total_solar_eclipse(self, params):
        results = scan_solar_eclipses(params, [self._ECLIPSE_2017])
        assert len(results) == 1
        r = results[0]
        assert r["detected"], (
            f"Expected detection; min_separation_arcmin={r['min_separation_arcmin']}"
        )
        # threshold is 0.8 degrees = 48 arcmin
        assert r["min_separation_arcmin"] < 48.0

    def test_returns_all_fields(self, params):
        results = scan_solar_eclipses(params, [self._ECLIPSE_2017])
        assert len(results) == 1
        assert set(results[0].keys()) == _EXPECTED_KEYS

    def test_empty_input(self, params):
        results = scan_solar_eclipses(params, [])
        assert results == []


class TestLunarScanner:
    # 2018-01-31 total lunar eclipse — JD 2458150.063194, magnitude 2.2941
    _ECLIPSE_2018 = {
        "julian_day_tt": 2458150.063194,
        "date": "2018-01-31T13:31:00",
        "type": "total",
        "magnitude": 2.2941,
    }

    def test_detects_known_lunar_eclipse(self, params):
        results = scan_lunar_eclipses(params, [self._ECLIPSE_2018])
        assert len(results) == 1
        r = results[0]
        assert r["detected"], (
            f"Expected detection; min_separation_arcmin={r['min_separation_arcmin']}, "
            f"threshold_arcmin={r['threshold_arcmin']}"
        )

    def test_returns_all_fields(self, params):
        results = scan_lunar_eclipses(params, [self._ECLIPSE_2018])
        assert len(results) == 1
        assert set(results[0].keys()) == _EXPECTED_KEYS

    def test_empty_input(self, params):
        results = scan_lunar_eclipses(params, [])
        assert results == []
