"""Eclipse scanning service — thin wrapper around tests/helpers.py logic."""
import numpy as np

from tychos_skyfield import baselib as T
from helpers import (
    scan_min_separation,
    scan_lunar_eclipse,
    MINUTE_IN_DAYS,
)

from server.db import get_db

HOUR_IN_DAYS = 1.0 / 24.0

# Detection thresholds (radians) — moved from helpers.py
SOLAR_DETECTION_THRESHOLD = 0.8 * (np.pi / 180)        # 0.8 degrees
LUNAR_UMBRAL_RADIUS = 0.45 * (np.pi / 180)             # 0.45 degrees
LUNAR_PENUMBRAL_RADIUS = 1.25 * (np.pi / 180)          # 1.25 degrees
MOON_MEAN_ANGULAR_RADIUS = 0.259 * (np.pi / 180)       # 0.259 degrees


def _lunar_threshold(catalog_type):
    """Get detection threshold for a lunar eclipse based on catalog type."""
    if catalog_type == "penumbral":
        return LUNAR_PENUMBRAL_RADIUS + MOON_MEAN_ANGULAR_RADIUS
    return LUNAR_UMBRAL_RADIUS + MOON_MEAN_ANGULAR_RADIUS


def _tychos_moon_velocity(system, jd, m_ra, m_dec):
    """Compute Moon RA/Dec velocity (radians per hour) at the given JD."""
    system.move_system(jd + HOUR_IN_DAYS)
    m_ra2, m_dec2, _ = system['moon'].radec_direct(system['earth'], epoch='j2000', formatted=False)
    system.move_system(jd)
    return float(m_ra2 - m_ra), float(m_dec2 - m_dec)


def load_eclipse_catalog(dataset_id: int) -> list[dict]:
    """Load eclipse catalog entries for a dataset from the DB."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT julian_day_tt, date, type, magnitude FROM eclipse_catalog WHERE dataset_id = ? ORDER BY julian_day_tt",
            (dataset_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def scan_solar_eclipses(params: dict, eclipses: list[dict]) -> list[dict]:
    """Run solar eclipse scan for the given params and eclipse list."""
    system = T.TychosSystem(params=params)
    threshold_arcmin = np.degrees(SOLAR_DETECTION_THRESHOLD) * 60
    rows = []

    for ecl in eclipses:
        jd = ecl["julian_day_tt"]
        min_sep, best_jd, s_ra, s_dec, m_ra, m_dec = scan_min_separation(system, jd)
        det = min_sep < SOLAR_DETECTION_THRESHOLD
        m_ra_vel, m_dec_vel = _tychos_moon_velocity(system, best_jd, float(m_ra), float(m_dec))

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
            "moon_ra_vel": m_ra_vel,
            "moon_dec_vel": m_dec_vel,
        })

    return rows


def scan_lunar_eclipses(params: dict, eclipses: list[dict]) -> list[dict]:
    """Run lunar eclipse scan for the given params and eclipse list."""
    system = T.TychosSystem(params=params)
    rows = []

    for ecl in eclipses:
        jd = ecl["julian_day_tt"]
        min_sep, best_jd, s_ra, s_dec, m_ra, m_dec = scan_lunar_eclipse(system, jd)
        threshold = _lunar_threshold(ecl["type"])
        threshold_arcmin = np.degrees(threshold) * 60
        det = min_sep < threshold
        m_ra_vel, m_dec_vel = _tychos_moon_velocity(system, best_jd, float(m_ra), float(m_dec))

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
            "moon_ra_vel": m_ra_vel,
            "moon_dec_vel": m_dec_vel,
        })

    return rows
