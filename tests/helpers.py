"""
Shared helper functions for Tychos eclipse prediction tests.
"""
import numpy as np
from tychos_skyfield import baselib as T

# --- Constants ---

MINUTE_IN_DAYS = 1.0 / 1440.0


def angular_separation(ra1, dec1, ra2, dec2):
    """Angular separation using the Vincenty formula. All inputs/output in radians."""
    dra = ra2 - ra1
    return np.arctan2(
        np.sqrt((np.cos(dec2) * np.sin(dra))**2 +
                (np.cos(dec1) * np.sin(dec2) -
                 np.sin(dec1) * np.cos(dec2) * np.cos(dra))**2),
        np.sin(dec1) * np.sin(dec2) + np.cos(dec1) * np.cos(dec2) * np.cos(dra)
    )


def _quadratic_refine(sep_fn, best_jd, dt=MINUTE_IN_DAYS):
    """Refine the JD of a sampled minimum via a 3-point parabolic fit.

    sep_fn(jd) -> (sep, pos) where pos is the 4-tuple (sun_ra, sun_dec, moon_ra, moon_dec).
    Samples at best_jd - dt, best_jd, best_jd + dt, fits a parabola to separation,
    and returns (best_sep, best_jd, best_pos) at the vertex. If the three points
    aren't concave-up (shouldn't happen at a true minimum), returns the center sample.
    """
    s_a, _ = sep_fn(best_jd - dt)
    s_b, pos_b = sep_fn(best_jd)
    s_c, _ = sep_fn(best_jd + dt)

    denom = s_a - 2.0 * s_b + s_c
    if denom <= 0:
        return s_b, best_jd, pos_b

    # Vertex offset in units of dt, clamped to the bracket.
    offset = 0.5 * (s_a - s_c) / denom
    if offset < -1.0 or offset > 1.0:
        return s_b, best_jd, pos_b

    refined_jd = best_jd + offset * dt
    refined_sep, refined_pos = sep_fn(refined_jd)
    if refined_sep < s_b:
        return refined_sep, refined_jd, refined_pos
    return s_b, best_jd, pos_b


def _get_sun_moon_radec(system):
    """Get Sun and Moon RA/Dec (radians) from a moved TychosSystem."""
    sun_ra, sun_dec, _ = system['sun'].radec_direct(
        system['earth'], epoch='j2000', formatted=False)
    moon_ra, moon_dec, _ = system['moon'].radec_direct(
        system['earth'], epoch='j2000', formatted=False)
    return sun_ra, sun_dec, moon_ra, moon_dec


def scan_min_separation(system, center_jd, half_window_hours=2):
    """Two-pass scan for minimum Sun-Moon angular separation.

    Returns (min_separation_rad, best_jd, sun_ra, sun_dec, moon_ra, moon_dec)
    where the positions are at the moment of minimum separation.
    """
    half_window = half_window_hours / 24.0
    coarse_step = 5 * MINUTE_IN_DAYS

    # Coarse pass
    jds = np.arange(center_jd - half_window, center_jd + half_window + coarse_step, coarse_step)
    best_sep = np.inf
    best_jd = center_jd
    best_pos = (0.0, 0.0, 0.0, 0.0)

    for jd in jds:
        system.move_system(jd)
        pos = _get_sun_moon_radec(system)
        sep = angular_separation(pos[0], pos[1], pos[2], pos[3])
        if sep < best_sep:
            best_sep = sep
            best_jd = jd
            best_pos = pos

    # Fine pass: +/-10 minutes around coarse minimum
    fine_step = MINUTE_IN_DAYS
    fine_half = 10 * MINUTE_IN_DAYS
    jds = np.arange(best_jd - fine_half, best_jd + fine_half + fine_step, fine_step)

    for jd in jds:
        system.move_system(jd)
        pos = _get_sun_moon_radec(system)
        sep = angular_separation(pos[0], pos[1], pos[2], pos[3])
        if sep < best_sep:
            best_sep = sep
            best_jd = jd
            best_pos = pos

    def sep_fn(jd):
        system.move_system(jd)
        pos = _get_sun_moon_radec(system)
        return angular_separation(pos[0], pos[1], pos[2], pos[3]), pos

    best_sep, best_jd, best_pos = _quadratic_refine(sep_fn, best_jd)
    return best_sep, best_jd, best_pos[0], best_pos[1], best_pos[2], best_pos[3]


def scan_lunar_eclipse(system, center_jd, half_window_hours=2):
    """Two-pass scan for minimum Moon-to-antisolar-point separation.

    Returns (min_separation_rad, best_jd, sun_ra, sun_dec, moon_ra, moon_dec)
    where the positions are at the moment of minimum separation.
    """
    half_window = half_window_hours / 24.0
    coarse_step = 5 * MINUTE_IN_DAYS

    # Coarse pass
    jds = np.arange(center_jd - half_window, center_jd + half_window + coarse_step, coarse_step)
    best_sep = np.inf
    best_jd = center_jd
    best_pos = (0.0, 0.0, 0.0, 0.0)

    for jd in jds:
        system.move_system(jd)
        pos = _get_sun_moon_radec(system)
        anti_ra = (pos[0] + np.pi) % (2 * np.pi)
        anti_dec = -pos[1]
        sep = angular_separation(pos[2], pos[3], anti_ra, anti_dec)
        if sep < best_sep:
            best_sep = sep
            best_jd = jd
            best_pos = pos

    # Fine pass
    fine_step = MINUTE_IN_DAYS
    fine_half = 10 * MINUTE_IN_DAYS
    jds = np.arange(best_jd - fine_half, best_jd + fine_half + fine_step, fine_step)

    for jd in jds:
        system.move_system(jd)
        pos = _get_sun_moon_radec(system)
        anti_ra = (pos[0] + np.pi) % (2 * np.pi)
        anti_dec = -pos[1]
        sep = angular_separation(pos[2], pos[3], anti_ra, anti_dec)
        if sep < best_sep:
            best_sep = sep
            best_jd = jd
            best_pos = pos

    def sep_fn(jd):
        system.move_system(jd)
        pos = _get_sun_moon_radec(system)
        anti_ra = (pos[0] + np.pi) % (2 * np.pi)
        anti_dec = -pos[1]
        return angular_separation(pos[2], pos[3], anti_ra, anti_dec), pos

    best_sep, best_jd, best_pos = _quadratic_refine(sep_fn, best_jd)
    return best_sep, best_jd, best_pos[0], best_pos[1], best_pos[2], best_pos[3]
