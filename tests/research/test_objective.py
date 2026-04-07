import pytest

from server.research.objective import compute_objective, EmptyResults


def _row(timing_offset_min, separation_arcmin=10.0, detected=1):
    return {
        "timing_offset_min": timing_offset_min,
        "min_separation_arcmin": separation_arcmin,
        "detected": detected,
    }


def test_objective_is_mean_abs_timing_offset():
    rows = [_row(2.0), _row(-4.0), _row(6.0)]
    assert compute_objective(rows) == pytest.approx((2 + 4 + 6) / 3)


def test_objective_handles_zero_offsets():
    rows = [_row(0.0), _row(0.0)]
    assert compute_objective(rows) == 0.0


def test_objective_raises_on_empty_results():
    with pytest.raises(EmptyResults):
        compute_objective([])


def test_objective_treats_negative_and_positive_symmetrically():
    a = compute_objective([_row(5.0)])
    b = compute_objective([_row(-5.0)])
    assert a == b == 5.0
