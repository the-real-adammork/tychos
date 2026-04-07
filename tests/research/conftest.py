import sys
from pathlib import Path

# Make sure tychos_skyfield, helpers, and the repo root are importable
_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_ROOT / "tychos_skyfield"))
sys.path.insert(0, str(_ROOT / "tests"))
sys.path.insert(0, str(_ROOT))


import pytest


# Three known eclipses used by the existing scanner tests — guaranteed to be
# detected by v1-original/v1 params.
_FIXTURE_ECLIPSES_SOLAR = [
    {
        "julian_day_tt": 2457987.268519,
        "date": "2017-08-21T18:26:40",
        "type": "total",
        "magnitude": 1.0306,
    },
    {
        "julian_day_tt": 2459883.953472,
        "date": "2022-10-25T11:00:00",
        "type": "partial",
        "magnitude": 0.86,
    },
    {
        "julian_day_tt": 2460388.819444,
        "date": "2024-04-08T18:20:00",
        "type": "total",
        "magnitude": 1.0566,
    },
]


@pytest.fixture
def fixture_solar_eclipses():
    return list(_FIXTURE_ECLIPSES_SOLAR)


@pytest.fixture
def patched_catalog_loader(monkeypatch, fixture_solar_eclipses):
    """Replace `load_eclipses_for_dataset` so init/validate don't touch the live DB."""
    from server.research import subset as subset_mod
    from server.research import cli as cli_mod

    def _fake(slug):
        if slug == "solar_eclipse":
            return list(fixture_solar_eclipses)
        return []

    monkeypatch.setattr(subset_mod, "load_eclipses_for_dataset", _fake)
    monkeypatch.setattr(cli_mod, "load_eclipses_for_dataset", _fake)
    return _fake


@pytest.fixture
def isolated_research_root(monkeypatch, tmp_path):
    """Point JobPaths.PARAMS_RESEARCH_ROOT at a tmp dir so tests don't pollute the repo."""
    from server.research import sandbox
    fake_root = tmp_path / "research"
    monkeypatch.setattr(sandbox, "PARAMS_RESEARCH_ROOT", fake_root)
    return fake_root
