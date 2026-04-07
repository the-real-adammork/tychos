"""Pure JPL/Skyfield eclipse scanner — no DB, no global state.

Extracted from server/seed.py so regression goldens can exercise the
compute path in isolation.
"""
import math
from typing import Iterable

import numpy as np
from skyfield.api import load as skyfield_load

from helpers import angular_separation  # tests/helpers.py is on sys.path


_MIN_IN_DAYS = 1.0 / 1440.0
_HOUR_IN_DAYS = 1.0 / 24.0


def scan_jpl_eclipses(
    eclipses: Iterable[dict],
    ephemeris_path: str,
    is_lunar: bool,
    half_window_hours: float = 2.0,
) -> list[dict]:
    """Compute JPL Sun/Moon positions and min-separation for a catalog.

    Pure function: reads the DE ephemeris from ephemeris_path, but does
    not touch any database or global mutable state. Returns one dict per
    input eclipse with keys matching the jpl_reference table columns
    (minus id/dataset_id).

    `half_window_hours` controls the ± search window used by the
    min-separation scan. Default 2.0 matches the current seed.py behavior
    (which the existing jpl_reference rows were produced with).
    """
    eph = skyfield_load(ephemeris_path)
    ts = skyfield_load.timescale()
    earth = eph["earth"]

    rows: list[dict] = []
    for ecl in eclipses:
        jd = ecl["julian_day_tt"]
        t = ts.tt_jd(jd)
        t2 = ts.tt_jd(jd + _HOUR_IN_DAYS)

        sun_ra, sun_dec, _ = earth.at(t).observe(eph["sun"]).radec()
        moon_ra, moon_dec, _ = earth.at(t).observe(eph["moon"]).radec()
        moon_ra2, moon_dec2, _ = earth.at(t2).observe(eph["moon"]).radec()

        s_ra, s_dec = sun_ra.radians, sun_dec.radians
        m_ra, m_dec = moon_ra.radians, moon_dec.radians
        m_ra_vel = float(moon_ra2.radians - m_ra)
        m_dec_vel = float(moon_dec2.radians - m_dec)

        if is_lunar:
            anti_ra = (s_ra + math.pi) % (2 * math.pi)
            anti_dec = -s_dec
            sep = float(np.degrees(angular_separation(m_ra, m_dec, anti_ra, anti_dec)) * 60)
        else:
            sep = float(np.degrees(angular_separation(s_ra, s_dec, m_ra, m_dec)) * 60)

        best_jd = _scan_jpl_min_jd(earth, eph, ts, jd, is_lunar, half_window_hours)

        rows.append({
            "julian_day_tt": jd,
            "sun_ra_rad": float(s_ra),
            "sun_dec_rad": float(s_dec),
            "moon_ra_rad": float(m_ra),
            "moon_dec_rad": float(m_dec),
            "separation_arcmin": round(sep, 2),
            "moon_ra_vel": m_ra_vel,
            "moon_dec_vel": m_dec_vel,
            "best_jd": best_jd,
        })

    return rows


def _scan_jpl_min_jd(
    earth,
    eph,
    ts,
    center_jd: float,
    is_lunar: bool,
    half_window_hours: float = 2.0,
) -> float:
    """Scan Skyfield for the JD of minimum separation.

    Two-pass (5-minute coarse, 1-minute fine) over ±half_window_hours around
    center_jd, then a 3-point quadratic refinement. Verbatim copy of the
    logic previously in server/seed.py::_scan_jpl_min_jd, with the
    previously-hardcoded 2h window lifted to a parameter (default 2.0
    preserves legacy behavior).
    """
    def sep_at(jd: float) -> float:
        t = ts.tt_jd(jd)
        s_ra, s_dec, _ = earth.at(t).observe(eph["sun"]).radec()
        m_ra, m_dec, _ = earth.at(t).observe(eph["moon"]).radec()
        s_ra_r, s_dec_r = s_ra.radians, s_dec.radians
        m_ra_r, m_dec_r = m_ra.radians, m_dec.radians
        if is_lunar:
            anti_ra = (s_ra_r + math.pi) % (2 * math.pi)
            anti_dec = -s_dec_r
            return float(angular_separation(m_ra_r, m_dec_r, anti_ra, anti_dec))
        return float(angular_separation(s_ra_r, s_dec_r, m_ra_r, m_dec_r))

    # Coarse pass: 5-minute steps across ±half_window_hours
    half_window_days = half_window_hours / 24.0
    best_jd = center_jd
    best_sep = float("inf")
    jd = center_jd - half_window_days
    end = center_jd + half_window_days + 1e-12
    while jd <= end:
        s = sep_at(jd)
        if s < best_sep:
            best_sep = s
            best_jd = jd
        jd += 5 * _MIN_IN_DAYS

    # Fine pass: 1-minute steps within +/-10min of coarse minimum
    jd = best_jd - 10 * _MIN_IN_DAYS
    end = best_jd + 10 * _MIN_IN_DAYS + 1e-12
    while jd <= end:
        s = sep_at(jd)
        if s < best_sep:
            best_sep = s
            best_jd = jd
        jd += _MIN_IN_DAYS

    # Quadratic refinement on the 3-point bracket
    s_a = sep_at(best_jd - _MIN_IN_DAYS)
    s_b = sep_at(best_jd)
    s_c = sep_at(best_jd + _MIN_IN_DAYS)
    denom = s_a - 2.0 * s_b + s_c
    if denom > 0:
        offset = 0.5 * (s_a - s_c) / denom
        if -1.0 <= offset <= 1.0:
            refined_jd = best_jd + offset * _MIN_IN_DAYS
            if sep_at(refined_jd) < s_b:
                return refined_jd
    return best_jd
