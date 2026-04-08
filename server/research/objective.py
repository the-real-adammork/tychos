"""Objective function for autoresearch iterations.

The single number the agent minimizes: mean per-eclipse positional error
between Tychos and JPL, in arcmin. Each eclipse's error is the Euclidean
magnitude of the four signed RA/Dec deltas for Sun and Moon sampled at
JPL's moment of minimum separation:

    err = sqrt(sun_dRA^2 + sun_dDec^2 + moon_dRA^2 + moon_dDec^2)

A change in either body's position in any direction moves the score, so
the agent can't optimize a mis-aligned Sun into a coincidentally-correct
Sun-Moon separation. Lower is better.

Rows without all four delta components (e.g. eclipses with no matching
JPL reference row) are excluded from the mean.
"""

import math


class EmptyResults(ValueError):
    """Raised when compute_objective is called with no results — likely a bug."""


class NoScorableResults(ValueError):
    """Raised when every row is missing delta components — objective undefined."""


def _row_positional_error(row: dict) -> float | None:
    """Return the per-eclipse positional error in arcmin, or None if incomplete."""
    s_ra = row.get("sun_delta_ra_arcmin")
    s_dec = row.get("sun_delta_dec_arcmin")
    m_ra = row.get("moon_delta_ra_arcmin")
    m_dec = row.get("moon_delta_dec_arcmin")
    if s_ra is None or s_dec is None or m_ra is None or m_dec is None:
        return None
    return math.sqrt(s_ra * s_ra + s_dec * s_dec + m_ra * m_ra + m_dec * m_dec)


def compute_objective(results: list[dict]) -> float:
    """Return mean per-eclipse positional error (arcmin) across results.

    Raises EmptyResults if `results` is empty, NoScorableResults if none of
    the rows carry the four delta components needed to compute the metric.
    """
    if not results:
        raise EmptyResults(
            "compute_objective called with empty results — "
            "the scan returned nothing, which usually means an empty subset or scan failure."
        )
    errs = [e for e in (_row_positional_error(r) for r in results) if e is not None]
    if not errs:
        raise NoScorableResults(
            "compute_objective: no rows had all four sun/moon delta fields — "
            "likely missing JPL reference data for this subset."
        )
    return sum(errs) / len(errs)


def aux_stats(results: list[dict]) -> dict:
    """Auxiliary stats printed alongside the objective for the agent's context.

    Not used in the optimization decision — purely informational. Reports
    mean sun/moon positional magnitude and event count.
    """
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
