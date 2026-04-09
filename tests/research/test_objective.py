import math

import pytest

from server.research.objective import (
    compute_objective,
    aux_stats,
    EmptyResults,
    NoScorableResults,
)


def _row(s_ra=0.0, s_dec=0.0, m_ra=0.0, m_dec=0.0):
    return {
        "sun_delta_ra_arcmin": s_ra,
        "sun_delta_dec_arcmin": s_dec,
        "moon_delta_ra_arcmin": m_ra,
        "moon_delta_dec_arcmin": m_dec,
    }


def test_objective_is_mean_euclidean_delta_magnitude():
    # Row 1: sqrt(1+1+1+1) = 2
    # Row 2: sqrt(0+0+9+16) = 5
    rows = [_row(1, 1, 1, 1), _row(0, 0, 3, 4)]
    assert compute_objective(rows) == pytest.approx((2 + 5) / 2)


def test_objective_handles_zero_deltas():
    rows = [_row(), _row()]
    assert compute_objective(rows) == 0.0


def test_objective_raises_on_empty_results():
    with pytest.raises(EmptyResults):
        compute_objective([])


def test_objective_raises_when_all_rows_missing_deltas():
    rows = [{"sun_delta_ra_arcmin": None, "sun_delta_dec_arcmin": None,
             "moon_delta_ra_arcmin": None, "moon_delta_dec_arcmin": None}]
    with pytest.raises(NoScorableResults):
        compute_objective(rows)


def test_objective_ignores_rows_missing_deltas():
    good = _row(3, 4, 0, 0)  # magnitude 5
    bad = {"sun_delta_ra_arcmin": None, "sun_delta_dec_arcmin": None,
           "moon_delta_ra_arcmin": None, "moon_delta_dec_arcmin": None}
    assert compute_objective([good, bad]) == pytest.approx(5.0)


def test_objective_treats_signs_symmetrically():
    a = compute_objective([_row(3, 0, 0, 4)])
    b = compute_objective([_row(-3, 0, 0, -4)])
    assert a == b == pytest.approx(5.0)


def test_aux_stats_reports_per_body_mean_magnitudes():
    rows = [_row(3, 4, 0, 0), _row(0, 0, 6, 8)]
    aux = aux_stats(rows)
    # Sun magnitudes: 5, 0 → mean 2.5 ; Moon magnitudes: 0, 10 → mean 5.0
    assert aux["mean_sun_error_arcmin"] == pytest.approx(2.5)
    assert aux["mean_moon_error_arcmin"] == pytest.approx(5.0)
    assert aux["n_total"] == 2


def test_solar_position_mode_uses_sun_only():
    rows = [_row(3, 4, 99, 99)]  # sun magnitude = 5, ignores moon
    assert compute_objective(rows, mode="solar_position") == pytest.approx(5.0)


def test_solar_position_mode_ignores_moon_deltas():
    # Even with None moon deltas, solar_position mode works
    row = {"sun_delta_ra_arcmin": 3.0, "sun_delta_dec_arcmin": 4.0,
           "moon_delta_ra_arcmin": None, "moon_delta_dec_arcmin": None}
    assert compute_objective([row], mode="solar_position") == pytest.approx(5.0)
