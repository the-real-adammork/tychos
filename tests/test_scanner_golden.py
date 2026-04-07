"""Golden-file regression tests for the eclipse scanners.

These tests load the full solar and lunar catalogs, run the pure
scan_solar_eclipses / scan_lunar_eclipses / scan_jpl_eclipses functions
with the v1-original/v1 parameter set, and compare every returned field
against frozen JSON goldens with exact equality.

They are marked @pytest.mark.slow because a full run is O(minutes). Run
with: pytest -m slow -v
"""
import json
import sys
from pathlib import Path

import pytest

# Mirror the sys.path setup used by tests/test_scanner.py
sys.path.insert(0, str(Path(__file__).parent.parent / "tychos_skyfield"))
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from server.services.scanner import scan_solar_eclipses, scan_lunar_eclipses
from server.services.jpl_scanner import scan_jpl_eclipses

_REPO_ROOT = Path(__file__).parent.parent
_PARAMS_PATH = _REPO_ROOT / "params" / "v1-original" / "v1.json"
_EPHEMERIS = str(_REPO_ROOT / "de440s.bsp")
_SOLAR_CATALOG = Path(__file__).parent / "data" / "solar_eclipses.json"
_LUNAR_CATALOG = Path(__file__).parent / "data" / "lunar_eclipses.json"
_GOLDENS = Path(__file__).parent / "data" / "goldens"

# Production window values as of 2026-04-07 (see plan + spec). These are
# deliberately hardcoded so the tests remain offline and do not depend on
# whatever datasets.scan_window_hours happens to be in the local DB.
_TYCHOS_HALF_WINDOW_HOURS = 6.0
_JPL_HALF_WINDOW_HOURS = 2.0  # seed.py has not been updated to per-dataset


@pytest.fixture(scope="module")
def params():
    with open(_PARAMS_PATH) as f:
        return json.load(f)["params"]


@pytest.fixture(scope="module")
def solar_catalog():
    with open(_SOLAR_CATALOG) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def lunar_catalog():
    with open(_LUNAR_CATALOG) as f:
        return json.load(f)


def _load_golden(name: str) -> list[dict]:
    with open(_GOLDENS / name) as f:
        return json.load(f)


def _assert_rows_equal(actual: list[dict], expected: list[dict], label: str) -> None:
    """Compare row lists with exact equality and produce a helpful diff."""
    assert len(actual) == len(expected), (
        f"{label}: row count mismatch — actual={len(actual)} expected={len(expected)}"
    )
    mismatches = []
    for i, (a, e) in enumerate(zip(actual, expected)):
        if set(a.keys()) != set(e.keys()):
            mismatches.append(
                f"  row {i} (jd={a.get('julian_day_tt')}): key mismatch "
                f"actual={sorted(a.keys())} expected={sorted(e.keys())}"
            )
            continue
        for k in sorted(e.keys()):
            if a[k] != e[k]:
                mismatches.append(
                    f"  row {i} (jd={a.get('julian_day_tt')}) field {k!r}: "
                    f"actual={a[k]!r} expected={e[k]!r}"
                )
        if len(mismatches) >= 20:
            mismatches.append("  ... (truncated at 20)")
            break
    if mismatches:
        raise AssertionError(
            f"{label}: {len(mismatches)} mismatched fields\n" + "\n".join(mismatches)
        )


@pytest.mark.slow
def test_solar_tychos_matches_golden(params, solar_catalog):
    expected = _load_golden("solar_tychos_v1.json")
    actual = scan_solar_eclipses(
        params, solar_catalog, half_window_hours=_TYCHOS_HALF_WINDOW_HOURS
    )
    _assert_rows_equal(actual, expected, "solar tychos")


@pytest.mark.slow
def test_lunar_tychos_matches_golden(params, lunar_catalog):
    expected = _load_golden("lunar_tychos_v1.json")
    actual = scan_lunar_eclipses(
        params, lunar_catalog, half_window_hours=_TYCHOS_HALF_WINDOW_HOURS
    )
    _assert_rows_equal(actual, expected, "lunar tychos")


@pytest.mark.slow
def test_solar_jpl_matches_golden(solar_catalog):
    expected = _load_golden("solar_jpl_v1.json")
    actual = scan_jpl_eclipses(
        solar_catalog,
        _EPHEMERIS,
        is_lunar=False,
        half_window_hours=_JPL_HALF_WINDOW_HOURS,
    )
    _assert_rows_equal(actual, expected, "solar jpl")


@pytest.mark.slow
def test_lunar_jpl_matches_golden(lunar_catalog):
    expected = _load_golden("lunar_jpl_v1.json")
    actual = scan_jpl_eclipses(
        lunar_catalog,
        _EPHEMERIS,
        is_lunar=True,
        half_window_hours=_JPL_HALF_WINDOW_HOURS,
    )
    _assert_rows_equal(actual, expected, "lunar jpl")
