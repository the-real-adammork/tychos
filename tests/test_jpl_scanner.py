"""Smoke test for server/services/jpl_scanner.scan_jpl_eclipses.

Verifies the extracted pure function runs on a single known eclipse and
returns the expected field set. Full regression coverage is in
test_scanner_golden.py.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "tychos_skyfield"))
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from server.services.jpl_scanner import scan_jpl_eclipses

_EPHEMERIS = str(Path(__file__).parent.parent / "de440s.bsp")

_EXPECTED_KEYS = {
    "julian_day_tt",
    "sun_ra_rad",
    "sun_dec_rad",
    "moon_ra_rad",
    "moon_dec_rad",
    "separation_arcmin",
    "moon_ra_vel",
    "moon_dec_vel",
    "best_jd",
    "sun_ra_at_best_rad",
    "sun_dec_at_best_rad",
    "moon_ra_at_best_rad",
    "moon_dec_at_best_rad",
}


def test_solar_single_eclipse():
    # 2017-08-21 total solar eclipse
    rows = scan_jpl_eclipses(
        [{"julian_day_tt": 2457987.268519}],
        _EPHEMERIS,
        is_lunar=False,
    )
    assert len(rows) == 1
    assert set(rows[0].keys()) == _EXPECTED_KEYS
    # Sun and Moon should be near each other (solar eclipse).
    # Note: catalog julian_day_tt is not necessarily peak; threshold is loose.
    assert rows[0]["separation_arcmin"] < 60.0


def test_lunar_single_eclipse():
    # 2018-01-31 total lunar eclipse
    rows = scan_jpl_eclipses(
        [{"julian_day_tt": 2458150.063194}],
        _EPHEMERIS,
        is_lunar=True,
    )
    assert len(rows) == 1
    assert set(rows[0].keys()) == _EXPECTED_KEYS
    # Moon should be very near the antisolar point (lunar eclipse)
    assert rows[0]["separation_arcmin"] < 60.0


def test_empty_input():
    assert scan_jpl_eclipses([], _EPHEMERIS, is_lunar=False) == []
