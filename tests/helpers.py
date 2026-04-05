"""
Shared helper functions for Tychos eclipse prediction tests.
"""
import numpy as np
from tychos_skyfield import baselib as T

# --- Constants ---

MINUTE_IN_DAYS = 1.0 / 1440.0

# Detection thresholds (radians)
SOLAR_DETECTION_THRESHOLD = 0.8 * (np.pi / 180)        # 0.8 degrees
LUNAR_UMBRAL_RADIUS = 0.45 * (np.pi / 180)             # 0.45 degrees
LUNAR_PENUMBRAL_RADIUS = 1.25 * (np.pi / 180)          # 1.25 degrees
MOON_MEAN_ANGULAR_RADIUS = 0.259 * (np.pi / 180)       # 0.259 degrees


def angular_separation(ra1, dec1, ra2, dec2):
    """Angular separation using the Vincenty formula. All inputs/output in radians."""
    dra = ra2 - ra1
    return np.arctan2(
        np.sqrt((np.cos(dec2) * np.sin(dra))**2 +
                (np.cos(dec1) * np.sin(dec2) -
                 np.sin(dec1) * np.cos(dec2) * np.cos(dra))**2),
        np.sin(dec1) * np.sin(dec2) + np.cos(dec1) * np.cos(dec2) * np.cos(dra)
    )


def _get_sun_moon_radec(system):
    """Get Sun and Moon RA/Dec (radians) from a moved TychosSystem."""
    sun_ra, sun_dec, _ = system['sun'].radec_direct(
        system['earth'], epoch='j2000', formatted=False)
    moon_ra, moon_dec, _ = system['moon'].radec_direct(
        system['earth'], epoch='j2000', formatted=False)
    return sun_ra, sun_dec, moon_ra, moon_dec


def scan_min_separation(system, center_jd, half_window_hours=2):
    """Two-pass scan for minimum Sun-Moon angular separation.

    Returns (min_separation_rad, best_jd).
    """
    half_window = half_window_hours / 24.0
    coarse_step = 5 * MINUTE_IN_DAYS

    # Coarse pass
    jds = np.arange(center_jd - half_window, center_jd + half_window + coarse_step, coarse_step)
    best_sep = np.inf
    best_jd = center_jd

    for jd in jds:
        system.move_system(jd)
        sun_ra, sun_dec, moon_ra, moon_dec = _get_sun_moon_radec(system)
        sep = angular_separation(sun_ra, sun_dec, moon_ra, moon_dec)
        if sep < best_sep:
            best_sep = sep
            best_jd = jd

    # Fine pass: +/-10 minutes around coarse minimum
    fine_step = MINUTE_IN_DAYS
    fine_half = 10 * MINUTE_IN_DAYS
    jds = np.arange(best_jd - fine_half, best_jd + fine_half + fine_step, fine_step)

    for jd in jds:
        system.move_system(jd)
        sun_ra, sun_dec, moon_ra, moon_dec = _get_sun_moon_radec(system)
        sep = angular_separation(sun_ra, sun_dec, moon_ra, moon_dec)
        if sep < best_sep:
            best_sep = sep
            best_jd = jd

    return best_sep, best_jd


def scan_lunar_eclipse(system, center_jd, half_window_hours=2):
    """Two-pass scan for minimum Moon-to-antisolar-point separation.

    Returns (min_separation_rad, best_jd).
    """
    half_window = half_window_hours / 24.0
    coarse_step = 5 * MINUTE_IN_DAYS

    # Coarse pass
    jds = np.arange(center_jd - half_window, center_jd + half_window + coarse_step, coarse_step)
    best_sep = np.inf
    best_jd = center_jd

    for jd in jds:
        system.move_system(jd)
        sun_ra, sun_dec, moon_ra, moon_dec = _get_sun_moon_radec(system)
        anti_ra = (sun_ra + np.pi) % (2 * np.pi)
        anti_dec = -sun_dec
        sep = angular_separation(moon_ra, moon_dec, anti_ra, anti_dec)
        if sep < best_sep:
            best_sep = sep
            best_jd = jd

    # Fine pass
    fine_step = MINUTE_IN_DAYS
    fine_half = 10 * MINUTE_IN_DAYS
    jds = np.arange(best_jd - fine_half, best_jd + fine_half + fine_step, fine_step)

    for jd in jds:
        system.move_system(jd)
        sun_ra, sun_dec, moon_ra, moon_dec = _get_sun_moon_radec(system)
        anti_ra = (sun_ra + np.pi) % (2 * np.pi)
        anti_dec = -sun_dec
        sep = angular_separation(moon_ra, moon_dec, anti_ra, anti_dec)
        if sep < best_sep:
            best_sep = sep
            best_jd = jd

    return best_sep, best_jd
