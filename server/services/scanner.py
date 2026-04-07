"""Eclipse scanning service — thin wrapper around tests/helpers.py logic."""
import numpy as np

from tychos_skyfield import baselib as T
from helpers import (
    scan_min_separation,
    scan_lunar_eclipse,
    MINUTE_IN_DAYS,
)

from server.db import get_db

import atexit
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor
from typing import Optional

# Module-level pool state, owned by the parent process. Not used inside
# worker subprocesses.
_POOL: Optional[ProcessPoolExecutor] = None
_POOL_HALF_WINDOW: Optional[float] = None

# Per-worker state, populated by _init_worker inside each subprocess.
# These names exist in the parent process too (initialized to None) but
# are only meaningful in worker processes.
_WORKER_HALF_WINDOW: Optional[float] = None
_WORKER_LAST_PARAMS: Optional[dict] = None
_WORKER_LAST_SYSTEM = None  # type: Optional[T.TychosSystem]

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


def scan_solar_eclipses(
    params: dict,
    eclipses: list[dict],
    half_window_hours: float = 2.0,
) -> list[dict]:
    """Run solar eclipse scan for the given params and eclipse list.

    `half_window_hours` controls the ± search window used to find each
    eclipse's minimum Sun-Moon separation. The default of 2.0 matches the
    production worker; research jobs may widen it to uncover true conjunctions
    that fall outside the default window.
    """
    system = T.TychosSystem(params=params)
    threshold_arcmin = np.degrees(SOLAR_DETECTION_THRESHOLD) * 60
    rows = []

    for ecl in eclipses:
        jd = ecl["julian_day_tt"]
        min_sep, best_jd, s_ra, s_dec, m_ra, m_dec = scan_min_separation(
            system, jd, half_window_hours=half_window_hours
        )
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


def scan_lunar_eclipses(
    params: dict,
    eclipses: list[dict],
    half_window_hours: float = 2.0,
) -> list[dict]:
    """Run lunar eclipse scan for the given params and eclipse list.

    `half_window_hours` controls the ± search window used to find each
    eclipse's minimum Moon-to-antisolar-point separation. See
    `scan_solar_eclipses` for rationale.
    """
    system = T.TychosSystem(params=params)
    rows = []

    for ecl in eclipses:
        jd = ecl["julian_day_tt"]
        min_sep, best_jd, s_ra, s_dec, m_ra, m_dec = scan_lunar_eclipse(
            system, jd, half_window_hours=half_window_hours
        )
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


# ---------------------------------------------------------------------------
# Worker-side helpers (run inside subprocess workers, called via the
# persistent ProcessPoolExecutor in _scan_*_eclipses_parallel).
# ---------------------------------------------------------------------------


def _init_worker(half_window_hours: float) -> None:
    """ProcessPoolExecutor initializer. Runs once per worker process."""
    global _WORKER_HALF_WINDOW
    _WORKER_HALF_WINDOW = half_window_hours


def _get_worker_system(params: dict):
    """LRU(1) cache for TychosSystem inside a worker process.

    Reuses the cached instance if `params` is unchanged from the previous
    task in this worker. Within a single batch (one scan_*_eclipses call),
    every task ships the same params dict, so the cache hits on every
    task after the first.
    """
    global _WORKER_LAST_PARAMS, _WORKER_LAST_SYSTEM
    if _WORKER_LAST_SYSTEM is not None and (
        _WORKER_LAST_PARAMS is params or _WORKER_LAST_PARAMS == params
    ):
        return _WORKER_LAST_SYSTEM
    _WORKER_LAST_SYSTEM = T.TychosSystem(params=params)
    _WORKER_LAST_PARAMS = params
    return _WORKER_LAST_SYSTEM


def _scan_one_solar_eclipse(task: tuple) -> dict:
    """Per-eclipse worker function for solar scans.

    `task` is (params, eclipse_dict). Returns the same row dict shape that
    scan_solar_eclipses produces in its serial loop.
    """
    params, ecl = task
    system = _get_worker_system(params)
    half_window = _WORKER_HALF_WINDOW
    threshold_arcmin = np.degrees(SOLAR_DETECTION_THRESHOLD) * 60

    jd = ecl["julian_day_tt"]
    min_sep, best_jd, s_ra, s_dec, m_ra, m_dec = scan_min_separation(
        system, jd, half_window_hours=half_window
    )
    det = min_sep < SOLAR_DETECTION_THRESHOLD
    m_ra_vel, m_dec_vel = _tychos_moon_velocity(system, best_jd, float(m_ra), float(m_dec))

    return {
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
    }


def _scan_one_lunar_eclipse(task: tuple) -> dict:
    """Per-eclipse worker function for lunar scans.

    `task` is (params, eclipse_dict). Returns the same row dict shape that
    scan_lunar_eclipses produces in its serial loop.
    """
    params, ecl = task
    system = _get_worker_system(params)
    half_window = _WORKER_HALF_WINDOW

    jd = ecl["julian_day_tt"]
    min_sep, best_jd, s_ra, s_dec, m_ra, m_dec = scan_lunar_eclipse(
        system, jd, half_window_hours=half_window
    )
    threshold = _lunar_threshold(ecl["type"])
    threshold_arcmin = np.degrees(threshold) * 60
    det = min_sep < threshold
    m_ra_vel, m_dec_vel = _tychos_moon_velocity(system, best_jd, float(m_ra), float(m_dec))

    return {
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
    }


def _get_or_create_pool(max_workers: int, half_window_hours: float) -> ProcessPoolExecutor:
    """Return a process pool initialized with the given half_window_hours.

    The pool persists across calls for the lifetime of the parent process.
    Rebuilds only when half_window_hours changes (rare in production).
    """
    global _POOL, _POOL_HALF_WINDOW
    if _POOL is not None and _POOL_HALF_WINDOW == half_window_hours:
        return _POOL
    if _POOL is not None:
        _POOL.shutdown(wait=True)
    _POOL = ProcessPoolExecutor(
        max_workers=max_workers,
        mp_context=mp.get_context("spawn"),
        initializer=_init_worker,
        initargs=(half_window_hours,),
    )
    _POOL_HALF_WINDOW = half_window_hours
    return _POOL


def _shutdown_pool() -> None:
    """atexit handler: shut down the persistent pool cleanly on parent exit."""
    global _POOL, _POOL_HALF_WINDOW
    if _POOL is not None:
        _POOL.shutdown(wait=True)
        _POOL = None
        _POOL_HALF_WINDOW = None


atexit.register(_shutdown_pool)


def _resolve_max_workers(max_workers: Optional[int]) -> int:
    """Resolve max_workers=None to the default (cpu_count - 1, min 1)."""
    if max_workers is not None:
        return max(1, max_workers)
    cpu = mp.cpu_count() or 1
    return max(1, cpu - 1)
