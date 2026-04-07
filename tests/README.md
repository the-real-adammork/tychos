# Tests

[← Back to README](../README.md)

Pytest-based test suite covering the eclipse scanner, the predicted geometry module, and shared helper math.

## Layout

```
tests/
├── conftest.py                    # Adds tychos_skyfield + repo root to sys.path
├── helpers.py                     # angular_separation, two-pass scan helpers, MINUTE_IN_DAYS
├── data/
│   ├── solar_eclipses.json        # Parsed NASA solar catalog (1901–2100)
│   └── lunar_eclipses.json        # Parsed NASA lunar catalog (1901–2100)
├── test_smoke.py                  # angular_separation correctness, TychosSystem sanity, scanner runs
├── test_predicted_geometry.py     # Catalog-derived geometry derivations
└── test_scanner.py                # End-to-end scanner against a known eclipse with v1 params
```

## Running

From the repo root:

```bash
source tychos_skyfield/.venv/bin/activate
PYTHONPATH=tychos_skyfield:tests:server:. python -m pytest tests/ -v
```

All 27 tests should pass with no DB setup needed — the tests load `params/v1-original/v1.json` from disk and don't touch SQLite.

## What's covered

| Test file | What it covers |
|---|---|
| `test_smoke.py::TestAngularSeparation` | Vincenty formula edge cases (identical points, 90°, 180°, near zero, poles) |
| `test_smoke.py::TestTychosSystemSanity` | The Tychos model produces non-NaN RA/Dec for Sun and Moon at the default JD; the two-pass scanners run without errors |
| `test_predicted_geometry.py::TestExpectedSeparationFromGamma` | gamma → angular separation projection |
| `test_predicted_geometry.py::TestSolarDiskRadii` | magnitude → Moon/Sun disk size derivation, including the partial-eclipse fallback |
| `test_predicted_geometry.py::TestLunarShadowRadii` | umbral/penumbral magnitude → shadow radii inversion |
| `test_predicted_geometry.py::TestApproachAngle` | gamma sign + ecliptic tilt → Moon approach direction |
| `test_scanner.py::TestSolarScanner` | The 2017 American total solar eclipse is detected and the result has all expected fields |
| `test_scanner.py::TestLunarScanner` | The 2018 super blue blood moon (total lunar) is detected with the expected fields |

## Adding tests

Tests are pure-Python and don't depend on the FastAPI server, the worker, or any database. Anything that needs the full stack should go in an integration suite (none exists yet) rather than here.
