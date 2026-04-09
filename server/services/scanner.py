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


def _sample_bodies_at(system, jd):
    """Move system to `jd` and return (sun_ra, sun_dec, moon_ra, moon_dec) in radians."""
    system.move_system(jd)
    s_ra, s_dec, _ = system['sun'].radec_direct(system['earth'], epoch='j2000', formatted=False)
    m_ra, m_dec, _ = system['moon'].radec_direct(system['earth'], epoch='j2000', formatted=False)
    return float(s_ra), float(s_dec), float(m_ra), float(m_dec)


def _add_jpl_sample(row, system, jpl_best_jd):
    """Populate tychos_*_at_jpl_rad fields on `row`. If jpl_best_jd is None, set all four to None."""
    if jpl_best_jd is None:
        row["tychos_sun_ra_at_jpl_rad"] = None
        row["tychos_sun_dec_at_jpl_rad"] = None
        row["tychos_moon_ra_at_jpl_rad"] = None
        row["tychos_moon_dec_at_jpl_rad"] = None
        return
    s_ra, s_dec, m_ra, m_dec = _sample_bodies_at(system, jpl_best_jd)
    row["tychos_sun_ra_at_jpl_rad"] = s_ra
    row["tychos_sun_dec_at_jpl_rad"] = s_dec
    row["tychos_moon_ra_at_jpl_rad"] = m_ra
    row["tychos_moon_dec_at_jpl_rad"] = m_dec


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
    *,
    jpl_best_jd_by_catalog_jd: Optional[dict] = None,
    max_workers: Optional[int] = None,
    parallel_threshold: int = 8,
) -> list[dict]:
    """Run solar eclipse scan for the given params and eclipse list.

    `half_window_hours` controls the ± search window used to find each
    eclipse's minimum Sun-Moon separation. The default of 2.0 matches the
    production worker; research jobs may widen it to uncover true conjunctions
    that fall outside the default window.

    `max_workers` controls process pool size. None (default) uses
    max(1, cpu_count() - 1). Pass 1 to force serial execution in-process.

    `parallel_threshold` is the smallest input length that triggers the
    process pool. Below this, the scan runs serially in-process to avoid
    pool spawn overhead. Default 8.
    """
    resolved_workers = _resolve_max_workers(max_workers)
    if resolved_workers == 1 or len(eclipses) < parallel_threshold:
        return _scan_solar_eclipses_serial(
            params, eclipses, half_window_hours, jpl_best_jd_by_catalog_jd
        )
    return _scan_solar_eclipses_parallel(
        params, eclipses, half_window_hours, resolved_workers, jpl_best_jd_by_catalog_jd
    )


def _scan_solar_eclipses_serial(
    params: dict, eclipses: list[dict], half_window_hours: float,
    jpl_best_jd_by_catalog_jd: Optional[dict] = None,
) -> list[dict]:
    """In-process serial path. Used for small inputs and max_workers=1."""
    system = T.TychosSystem(params=params, bodies=["sun", "moon"])
    threshold_arcmin = np.degrees(SOLAR_DETECTION_THRESHOLD) * 60
    rows = []

    for ecl in eclipses:
        jd = ecl["julian_day_tt"]
        min_sep, best_jd, s_ra, s_dec, m_ra, m_dec = scan_min_separation(
            system, jd, half_window_hours=half_window_hours
        )
        det = min_sep < SOLAR_DETECTION_THRESHOLD
        m_ra_vel, m_dec_vel = _tychos_moon_velocity(system, best_jd, float(m_ra), float(m_dec))

        row = {
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
        jpl_best = (jpl_best_jd_by_catalog_jd or {}).get(jd)
        _add_jpl_sample(row, system, jpl_best)
        rows.append(row)

    return rows


def _scan_solar_eclipses_parallel(
    params: dict,
    eclipses: list[dict],
    half_window_hours: float,
    max_workers: int,
    jpl_best_jd_by_catalog_jd: Optional[dict] = None,
) -> list[dict]:
    """Parallel path: ship (params, eclipse) tasks to a persistent process pool."""
    pool = _get_or_create_pool(max_workers, half_window_hours)
    lookup = jpl_best_jd_by_catalog_jd or {}
    tasks = [(params, ecl, lookup.get(ecl["julian_day_tt"])) for ecl in eclipses]
    return list(pool.map(_scan_one_solar_eclipse, tasks))


def scan_lunar_eclipses(
    params: dict,
    eclipses: list[dict],
    half_window_hours: float = 2.0,
    *,
    jpl_best_jd_by_catalog_jd: Optional[dict] = None,
    max_workers: Optional[int] = None,
    parallel_threshold: int = 8,
) -> list[dict]:
    """Run lunar eclipse scan for the given params and eclipse list.

    See `scan_solar_eclipses` for the meaning of `half_window_hours`,
    `max_workers`, and `parallel_threshold`.
    """
    resolved_workers = _resolve_max_workers(max_workers)
    if resolved_workers == 1 or len(eclipses) < parallel_threshold:
        return _scan_lunar_eclipses_serial(
            params, eclipses, half_window_hours, jpl_best_jd_by_catalog_jd
        )
    return _scan_lunar_eclipses_parallel(
        params, eclipses, half_window_hours, resolved_workers, jpl_best_jd_by_catalog_jd
    )


def _scan_lunar_eclipses_serial(
    params: dict, eclipses: list[dict], half_window_hours: float,
    jpl_best_jd_by_catalog_jd: Optional[dict] = None,
) -> list[dict]:
    """In-process serial path. Used for small inputs and max_workers=1."""
    system = T.TychosSystem(params=params, bodies=["sun", "moon"])
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

        row = {
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
        jpl_best = (jpl_best_jd_by_catalog_jd or {}).get(jd)
        _add_jpl_sample(row, system, jpl_best)
        rows.append(row)

    return rows


def _scan_lunar_eclipses_parallel(
    params: dict,
    eclipses: list[dict],
    half_window_hours: float,
    max_workers: int,
    jpl_best_jd_by_catalog_jd: Optional[dict] = None,
) -> list[dict]:
    """Parallel path: ship (params, eclipse) tasks to a persistent process pool."""
    pool = _get_or_create_pool(max_workers, half_window_hours)
    lookup = jpl_best_jd_by_catalog_jd or {}
    tasks = [(params, ecl, lookup.get(ecl["julian_day_tt"])) for ecl in eclipses]
    return list(pool.map(_scan_one_lunar_eclipse, tasks))


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
    _WORKER_LAST_SYSTEM = T.TychosSystem(params=params, bodies=["sun", "moon"])
    _WORKER_LAST_PARAMS = params
    return _WORKER_LAST_SYSTEM


def _scan_one_solar_eclipse(task: tuple) -> dict:
    """Per-eclipse worker function for solar scans.

    `task` is (params, eclipse_dict, jpl_best_jd_or_none). Returns the same
    row dict shape that scan_solar_eclipses produces in its serial loop.
    """
    params, ecl, jpl_best = task
    system = _get_worker_system(params)
    half_window = _WORKER_HALF_WINDOW
    threshold_arcmin = np.degrees(SOLAR_DETECTION_THRESHOLD) * 60

    jd = ecl["julian_day_tt"]
    min_sep, best_jd, s_ra, s_dec, m_ra, m_dec = scan_min_separation(
        system, jd, half_window_hours=half_window
    )
    det = min_sep < SOLAR_DETECTION_THRESHOLD
    m_ra_vel, m_dec_vel = _tychos_moon_velocity(system, best_jd, float(m_ra), float(m_dec))

    row = {
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
    _add_jpl_sample(row, system, jpl_best)
    return row


def _scan_one_lunar_eclipse(task: tuple) -> dict:
    """Per-eclipse worker function for lunar scans.

    `task` is (params, eclipse_dict, jpl_best_jd_or_none). Returns the same
    row dict shape that scan_lunar_eclipses produces in its serial loop.
    """
    params, ecl, jpl_best = task
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

    row = {
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
    _add_jpl_sample(row, system, jpl_best)
    return row


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
