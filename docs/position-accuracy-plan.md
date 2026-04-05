# Tychos Position Accuracy Test Plan

## Goal

Measure how accurately the Tychos model positions each celestial body compared to JPL ephemeris data over time.

## Prerequisites

- Python 3.12+
- Git submodules initialized: `git submodule update --init --recursive`
- Install dependencies: `pip install -r requirements.txt`
- First run will auto-download DE440 ephemeris (~100MB, cached by Skyfield)

## Output Goals

The tests produce raw results — no pass/fail judgments baked in. For each body at each sample date, report the angular error vs JPL. Interpretation is left to the reader.

## Data Source

### JPL DE440 Ephemeris Files (primary)

- URL: https://ssd.jpl.nasa.gov/ftp/eph/planets/bsp/
- Binary SPK files, DE440 covers 1550-2650
- Loaded locally by Skyfield for fast bulk computation
- Covers: Sun, Moon, Mercury, Venus, Mars, Jupiter, Saturn, Uranus, Neptune

### JPL HORIZONS (supplementary, for small bodies)

- URL: https://ssd.jpl.nasa.gov/horizons/
- REST API, no key required
- Python access: `astroquery.jplhorizons`
- Only needed if testing Eros; Halley's Comet is excluded (see below)

Note: DE440 does not include comets or asteroids. Halley's Comet is excluded. Eros can be tested using a separate small-body SPK kernel if desired, but is low priority. Phobos and Deimos are excluded — they are not interesting targets for sky-position accuracy.

## Test Architecture

```
tychos/
  TSN/                              # submodule
  tychos_skyfield/                  # submodule
  tests/
    conftest.py                     # shared fixtures and helpers
    test_position_accuracy.py       # Tychos vs JPL for planets over time
  requirements.txt
```

## Method

Use the `skyfieldlib.Ephemeris` wrapper so both Tychos and Skyfield positions are computed through the same Skyfield API:

```python
from skyfield.api import load
from tychos_skyfield import skyfieldlib as TS

eph_jpl = load('de440.bsp')
earth_ref = TS.ReferencePlanet('Earth', eph_jpl)
eph_tychos = TS.Ephemeris(earth_ref)

earth = eph_jpl['earth']

# JPL reference position:
ra_jpl, dec_jpl, _ = earth.at(t).observe(eph_jpl['mars']).radec()

# Tychos position (observed from JPL Earth — intentional, so the observer
# is identical and only the target body position differs):
ra_tychos, dec_tychos, _ = earth.at(t).observe(eph_tychos['mars']).radec()
```

Note: `eph_tychos['earth']` returns the JPL Earth object (by design in the `Ephemeris` class). This means both measurements share the same observer position, isolating the comparison to the target body's predicted position only.

The `.radec()` call on an `.observe()` result returns astrometric ICRF coordinates (no precession/nutation), which is the correct frame for comparing model accuracy.

Compute angular error using the Vincenty formula. Sample at monthly intervals over 1900-2100 (2400 points per body).

## Bodies to Test

Planets available in both Tychos and DE440: Sun, Moon, Mercury, Venus, Mars, Jupiter, Saturn, Uranus, Neptune.

## Expected Output

Per-body accuracy table:

```
Body     | 1950-2000 RMS | 2000-2050 RMS | Max Error
---------|---------------|---------------|----------
Sun      |               |               |
Moon     |               |               |
Mercury  |               |               |
Venus    |               |               |
Mars     |               |               |
Jupiter  |               |               |
Saturn   |               |               |
Uranus   |               |               |
Neptune  |               |               |
```

Also output CSV files with per-date errors for time-series analysis. This reveals where errors start growing — indicating the effective validity range of the model's parameter fit.
