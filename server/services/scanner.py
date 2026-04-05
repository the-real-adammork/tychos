"""Eclipse scanning service — thin wrapper around tests/helpers.py logic."""
import json
from pathlib import Path

import numpy as np

# tychos_skyfield and helpers are expected on PYTHONPATH (set by the caller).
from tychos_skyfield import baselib as T
from helpers import (
    scan_min_separation,
    scan_lunar_eclipse,
    lunar_threshold,
    SOLAR_DETECTION_THRESHOLD,
    MINUTE_IN_DAYS,
)

DATA_DIR = Path(__file__).parent.parent.parent / "tests" / "data"


def load_eclipse_catalog(test_type: str) -> list[dict]:
    """Load solar or lunar eclipse catalog from tests/data."""
    path = DATA_DIR / f"{test_type}_eclipses.json"
    with open(path) as f:
        return json.load(f)


def scan_solar_eclipses(params: dict, eclipses: list[dict]) -> list[dict]:
    """Run solar eclipse scan for the given params and eclipse list.

    Returns a list of result dicts matching the eclipse_results schema.
    """
    system = T.TychosSystem(params=params)
    threshold_arcmin = np.degrees(SOLAR_DETECTION_THRESHOLD) * 60
    rows = []

    for ecl in eclipses:
        jd = ecl["julian_day_tt"]
        min_sep, best_jd, s_ra, s_dec, m_ra, m_dec = scan_min_separation(system, jd)
        det = min_sep < SOLAR_DETECTION_THRESHOLD

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

    return rows


def scan_lunar_eclipses(params: dict, eclipses: list[dict]) -> list[dict]:
    """Run lunar eclipse scan for the given params and eclipse list.

    Returns a list of result dicts matching the eclipse_results schema.
    """
    system = T.TychosSystem(params=params)
    rows = []

    for ecl in eclipses:
        jd = ecl["julian_day_tt"]
        min_sep, best_jd, s_ra, s_dec, m_ra, m_dec = scan_lunar_eclipse(system, jd)
        threshold = lunar_threshold(ecl["type"])
        threshold_arcmin = np.degrees(threshold) * 60
        det = min_sep < threshold

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

    return rows
