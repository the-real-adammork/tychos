"""Objective function for autoresearch iterations.

Supports two modes:

  combined (default):
    err = sqrt(sun_dRA^2 + sun_dDec^2 + moon_dRA^2 + moon_dDec^2)

  solar_position:
    err = sqrt(sun_dRA^2 + sun_dDec^2)

Both report mean per-eclipse error in arcmin. Lower is better.
"""

import math

MODES = ("combined", "solar_position")


class EmptyResults(ValueError):
    """Raised when compute_objective is called with no results — likely a bug."""


class NoScorableResults(ValueError):
    """Raised when every row is missing delta components — objective undefined."""


def _row_error(row: dict, mode: str) -> float | None:
    """Return the per-eclipse error in arcmin for the given mode, or None if incomplete."""
    s_ra = row.get("sun_delta_ra_arcmin")
    s_dec = row.get("sun_delta_dec_arcmin")
    if s_ra is None or s_dec is None:
        return None
    if mode == "solar_position":
        return math.sqrt(s_ra * s_ra + s_dec * s_dec)
    # combined
    m_ra = row.get("moon_delta_ra_arcmin")
    m_dec = row.get("moon_delta_dec_arcmin")
    if m_ra is None or m_dec is None:
        return None
    return math.sqrt(s_ra * s_ra + s_dec * s_dec + m_ra * m_ra + m_dec * m_dec)


def compute_objective(results: list[dict], mode: str = "combined") -> float:
    """Return mean per-eclipse error (arcmin) across results.

    Raises EmptyResults if `results` is empty, NoScorableResults if none of
    the rows carry the delta components needed for the chosen mode.
    """
    if mode not in MODES:
        raise ValueError(f"Unknown objective mode: {mode!r}. Valid: {MODES}")
    if not results:
        raise EmptyResults(
            "compute_objective called with empty results — "
            "the scan returned nothing, which usually means an empty subset or scan failure."
        )
    errs = [e for e in (_row_error(r, mode) for r in results) if e is not None]
    if not errs:
        raise NoScorableResults(
            f"compute_objective({mode}): no rows had the required delta fields — "
            "likely missing JPL reference data for this subset."
        )
    return sum(errs) / len(errs)


def per_eclipse_detail(results: list[dict], mode: str = "combined") -> list[dict]:
    """Return per-eclipse date + signed deltas + error magnitude, sorted worst-first.

    Used to give the AI agent visibility into which eclipses are worst and
    the signed direction of each body's error.
    """
    details = []
    for r in results:
        err = _row_error(r, mode)
        if err is None:
            continue
        entry = {
            "date": r.get("date", "?"),
            "error": round(err, 4),
            "sun_dRA": round(r["sun_delta_ra_arcmin"], 4),
            "sun_dDec": round(r["sun_delta_dec_arcmin"], 4),
        }
        if mode == "combined":
            entry["moon_dRA"] = round(r.get("moon_delta_ra_arcmin", 0), 4)
            entry["moon_dDec"] = round(r.get("moon_delta_dec_arcmin", 0), 4)
        details.append(entry)
    details.sort(key=lambda d: -d["error"])
    return details


def aux_stats(results: list[dict]) -> dict:
    """Auxiliary stats printed alongside the objective for the agent's context."""
    if not results:
        return {
            "mean_sun_error_arcmin": None,
            "mean_moon_error_arcmin": None,
            "n_total": 0,
        }
    n_total = len(results)

    def _mag(ra, dec):
        if ra is None or dec is None:
            return None
        return math.sqrt(ra * ra + dec * dec)

    sun_mags = [
        _mag(r.get("sun_delta_ra_arcmin"), r.get("sun_delta_dec_arcmin")) for r in results
    ]
    moon_mags = [
        _mag(r.get("moon_delta_ra_arcmin"), r.get("moon_delta_dec_arcmin")) for r in results
    ]
    sun_mags = [m for m in sun_mags if m is not None]
    moon_mags = [m for m in moon_mags if m is not None]

    return {
        "mean_sun_error_arcmin": round(sum(sun_mags) / len(sun_mags), 3) if sun_mags else None,
        "mean_moon_error_arcmin": round(sum(moon_mags) / len(moon_mags), 3) if moon_mags else None,
        "n_total": n_total,
    }
