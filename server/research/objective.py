"""Objective function for autoresearch iterations.

The single number the agent minimizes: mean absolute timing offset (in minutes)
across the result rows of one scan. Lower is better.
"""


class EmptyResults(ValueError):
    """Raised when compute_objective is called with no results — likely a bug."""


def compute_objective(results: list[dict]) -> float:
    """Return mean(|timing_offset_min|) across results.

    Raises EmptyResults if `results` is empty (silent zero would mask bugs).
    """
    if not results:
        raise EmptyResults(
            "compute_objective called with empty results — "
            "the scan returned nothing, which usually means an empty subset or scan failure."
        )
    total = sum(abs(r["timing_offset_min"]) for r in results)
    return total / len(results)


def aux_stats(results: list[dict]) -> dict:
    """Auxiliary stats printed alongside the objective for the agent's context.

    Not used in the optimization decision — purely informational. Reports
    mean angular separation (the "Tychos error") alongside the event count.
    Detection rate is intentionally omitted: it's a binary threshold signal
    that can mask real progress in the continuous timing + separation metrics.
    """
    if not results:
        return {"mean_separation_arcmin": None, "n_total": 0}
    n_total = len(results)
    mean_sep = sum(r["min_separation_arcmin"] for r in results) / n_total
    return {
        "mean_separation_arcmin": round(mean_sep, 3),
        "n_total": n_total,
    }
