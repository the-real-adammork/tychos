"""
Scanner service — pure computation, no database.

Wraps the eclipse scan helpers from tests/helpers.py and exposes
two public functions: scan_solar_eclipses and scan_lunar_eclipses.
"""
import json
import sys
from pathlib import Path

# Allow imports of tychos_skyfield and tests/helpers from anywhere
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "tychos_skyfield"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "tests"))

import numpy as np
from tychos_skyfield import baselib as T
from helpers import (
    scan_min_separation,
    scan_lunar_eclipse,
    lunar_threshold,
    SOLAR_DETECTION_THRESHOLD,
    MINUTE_IN_DAYS,
)

_DATA_DIR = Path(__file__).parent.parent.parent / "tests" / "data"


def load_eclipse_catalog(test_type: str) -> list[dict]:
    """Load solar or lunar eclipse catalog from tests/data/.

    Args:
        test_type: "solar" or "lunar"

    Returns:
        List of eclipse dicts with keys: julian_day_tt, date, type, magnitude.
    """
    path = _DATA_DIR / f"{test_type}_eclipses.json"
    with open(path) as f:
        return json.load(f)


def scan_solar_eclipses(params: dict, eclipses: list[dict]) -> list[dict]:
    """Scan a list of solar eclipse candidates against a Tychos parameter set.

    Args:
        params:   TychosSystem parameter dict (contents of a params/*.json file).
        eclipses: List of eclipse dicts, each with julian_day_tt, date, type, magnitude.

    Returns:
        List of result dicts with snake_case keys describing each eclipse outcome.
    """
    if not eclipses:
        return []

    system = T.TychosSystem(params=params)
    threshold_rad = SOLAR_DETECTION_THRESHOLD
    threshold_arcmin = np.degrees(threshold_rad) * 60
    results = []

    for ecl in eclipses:
        jd = ecl["julian_day_tt"]
        min_sep, best_jd, s_ra, s_dec, m_ra, m_dec = scan_min_separation(system, jd)

        detected = bool(min_sep < threshold_rad)
        results.append({
            "julian_day_tt": jd,
            "date": ecl["date"],
            "catalog_type": ecl["type"],
            "magnitude": ecl["magnitude"],
            "detected": detected,
            "threshold_arcmin": round(threshold_arcmin, 4),
            "min_separation_arcmin": round(float(np.degrees(min_sep) * 60), 2),
            "timing_offset_min": round((best_jd - jd) / MINUTE_IN_DAYS, 1),
            "best_jd": best_jd,
            "sun_ra_rad": float(s_ra),
            "sun_dec_rad": float(s_dec),
            "moon_ra_rad": float(m_ra),
            "moon_dec_rad": float(m_dec),
        })

    return results


def scan_lunar_eclipses(params: dict, eclipses: list[dict]) -> list[dict]:
    """Scan a list of lunar eclipse candidates against a Tychos parameter set.

    Args:
        params:   TychosSystem parameter dict (contents of a params/*.json file).
        eclipses: List of eclipse dicts, each with julian_day_tt, date, type, magnitude.

    Returns:
        List of result dicts with snake_case keys describing each eclipse outcome.
    """
    if not eclipses:
        return []

    system = T.TychosSystem(params=params)
    results = []

    for ecl in eclipses:
        jd = ecl["julian_day_tt"]
        catalog_type = ecl["type"]
        min_sep, best_jd, s_ra, s_dec, m_ra, m_dec = scan_lunar_eclipse(system, jd)

        threshold_rad = lunar_threshold(catalog_type)
        threshold_arcmin = np.degrees(threshold_rad) * 60
        detected = bool(min_sep < threshold_rad)
        results.append({
            "julian_day_tt": jd,
            "date": ecl["date"],
            "catalog_type": catalog_type,
            "magnitude": ecl["magnitude"],
            "detected": detected,
            "threshold_arcmin": round(threshold_arcmin, 4),
            "min_separation_arcmin": round(float(np.degrees(min_sep) * 60), 2),
            "timing_offset_min": round((best_jd - jd) / MINUTE_IN_DAYS, 1),
            "best_jd": best_jd,
            "sun_ra_rad": float(s_ra),
            "sun_dec_rad": float(s_dec),
            "moon_ra_rad": float(m_ra),
            "moon_dec_rad": float(m_dec),
        })

    return results
