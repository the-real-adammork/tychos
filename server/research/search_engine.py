"""Joint multi-parameter search using Nelder-Mead.

The single-parameter coordinate descent an agent does by hand ("bump
moon.start_pos, measure, revert or keep") is slow and gets stuck at
single-parameter local minima. This module exposes `run_search`, a
Nelder-Mead wrapper that lets the agent hand off a focused set of
parameters and a budget, then receive the best joint assignment it
could find.

Design notes:
- We use scipy.optimize.minimize(method="Nelder-Mead") because it is
  derivative-free (the objective is computed by running the scanner —
  no closed-form gradient), handles the modest number of free
  parameters the agent will realistically hand it (~2–10), and is in
  stdlib-adjacent scipy which is already a transitive dep of the
  project.
- The initial simplex is constructed by perturbing each coordinate
  by max(scale * |x0|, ABS_FLOOR) so zero-valued starting coordinates
  (which are common — several orbit_center_* fields in v1 are 0) still
  get a meaningful probe step.
- Every accepted/rejected simplex vertex is counted toward the budget
  (`maxfev`). Scipy may also terminate early on `xatol`/`fatol`.
- The caller is responsible for validating the parameter list against
  the job's allowlist *before* calling run_search — this module is
  optimizer-only and does not know about program.md.
"""
from dataclasses import dataclass
from typing import Callable

import numpy as np
from scipy.optimize import minimize


ABS_FLOOR = 1e-4  # minimum simplex step for zero-valued coordinates


@dataclass
class SearchResult:
    """Outcome of a single search run."""
    starting_objective: float
    best_objective: float
    best_params: dict
    n_evals: int
    converged: bool
    message: str


def _get_nested(params: dict, key: str) -> float:
    """Read `body.field` from a params dict."""
    body, field = key.split(".", 1)
    return float(params[body][field])


def _set_nested(params: dict, key: str, value: float) -> None:
    """Write `body.field` into a params dict (mutates in place)."""
    body, field = key.split(".", 1)
    params[body][field] = float(value)


def run_search(
    *,
    current: dict,
    param_keys: list[str],
    evaluate: Callable[[dict], float],
    budget: int = 50,
    scale: float = 0.01,
) -> SearchResult:
    """Run Nelder-Mead over `param_keys`, minimizing `evaluate(candidate_params)`.

    `current` is the params dict to start from. It is not mutated —
    the returned `best_params` is a deep-copied dict with only the
    searched keys replaced by the best found values.

    `evaluate` is the objective function the caller supplies. It takes
    a candidate params dict (a copy of `current` with the searched
    keys overwritten) and returns a float to minimize. Typically this
    runs the scanner against a fixed subset and computes
    mean(|timing_offset_min|). The caller is responsible for any error
    handling (e.g., catching scanner exceptions and returning +inf).

    `budget` bounds the total number of calls to `evaluate`.
    `scale` sets the initial simplex step as a fraction of each
    starting coordinate (with ABS_FLOOR for zeros).
    """
    import copy

    if not param_keys:
        raise ValueError("run_search called with no parameters to search")
    if budget < len(param_keys) + 1:
        raise ValueError(
            f"budget={budget} too small for {len(param_keys)} params "
            f"(Nelder-Mead needs ≥ n+1 evaluations to form the initial simplex)"
        )

    x0 = np.array([_get_nested(current, k) for k in param_keys], dtype=float)

    # Build an explicit initial simplex. scipy's default is 5% of each
    # coordinate which collapses to zero for zero-valued starting params.
    n = len(x0)
    simplex = np.empty((n + 1, n), dtype=float)
    simplex[0] = x0
    for i in range(n):
        vertex = x0.copy()
        step = max(scale * abs(x0[i]), ABS_FLOOR)
        vertex[i] = x0[i] + step
        simplex[i + 1] = vertex

    starting_candidate = copy.deepcopy(current)
    starting_objective = evaluate(starting_candidate)

    evals_remaining = [budget - 1]  # account for the starting evaluation

    def _objective(x: np.ndarray) -> float:
        if evals_remaining[0] <= 0:
            # Scipy has no native "stop after N fevals" hook; returning a
            # large constant effectively tells Nelder-Mead "no more improvement
            # available" and it will terminate on xatol.
            return float("inf")
        evals_remaining[0] -= 1
        candidate = copy.deepcopy(current)
        for key, val in zip(param_keys, x):
            _set_nested(candidate, key, val)
        try:
            return float(evaluate(candidate))
        except Exception:
            return float("inf")

    result = minimize(
        _objective,
        x0,
        method="Nelder-Mead",
        options={
            "initial_simplex": simplex,
            # Scipy counts its own evaluations; we already consumed one
            # evaluating the starting point, so leave room for budget - 1.
            "maxfev": max(budget - 1, len(x0) + 1),
            "xatol": 1e-8,
            "fatol": 1e-4,
            "adaptive": True,
        },
    )

    n_evals = int(result.nfev) + 1  # + 1 for the starting evaluation we did ourselves

    best_x = result.x if result.fun < starting_objective else x0
    best_obj = float(min(result.fun, starting_objective))

    best_params = copy.deepcopy(current)
    for key, val in zip(param_keys, best_x):
        _set_nested(best_params, key, val)

    return SearchResult(
        starting_objective=float(starting_objective),
        best_objective=best_obj,
        best_params=best_params,
        n_evals=n_evals,
        converged=bool(result.success),
        message=str(result.message),
    )
