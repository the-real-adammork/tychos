# Tychos Eclipse Prediction Test Plan

## Goal

Test the Tychos solar system model's ability to predict solar and lunar eclipses using the NASA eclipse catalog as reference.

## Prerequisites

- Python 3.12+
- Git submodules initialized: `git submodule update --init --recursive`
- Install dependencies: `pip install -r requirements.txt`
- `tychos_skyfield` is used as a path dependency (no setup.py needed, just PYTHONPATH or pip install -e)

## Output Goals

The tests produce raw results — no pass/fail judgments baked in. Report the data and let it speak for itself:

- For every eclipse in the NASA catalog, report whether Tychos predicts it, the minimum angular separation achieved, and the timing offset from the catalog peak

Interpretation of what constitutes "good enough" is left to the reader.

## Data Source

### NASA Eclipse Catalogs

- **NASA Five Millennium Canon of Solar Eclipses**
  - URL: https://eclipse.gsfc.nasa.gov/SEcat5/catalog.html
  - Fixed-width text, covers -1999 to +3000, freely downloadable
  - Fields: eclipse type, peak time (in TT), magnitude, coordinates

- **NASA Five Millennium Canon of Lunar Eclipses**
  - URL: https://eclipse.gsfc.nasa.gov/LEcat5/catalog.html
  - Same format and coverage as solar catalog

A parser script (`scripts/parse_nasa_eclipses.py`) converts the fixed-width NASA catalog files into JSON. Output schema:

```json
{
  "julian_day_tt": 2451545.0,
  "date": "2000-01-01T12:00:00",
  "type": "total",
  "magnitude": 1.024
}
```

## Time Scale

Both the NASA eclipse catalogs and Tychos `move_system()` use Terrestrial Time (TT). No UTC-to-TT conversion is needed. All Julian dates in test data and code are TT.

## Test Architecture

```
tychos/
  TSN/                              # submodule
  tychos_skyfield/                  # submodule
  scripts/
    parse_nasa_eclipses.py          # NASA fixed-width catalog -> JSON
  tests/
    data/
      solar_eclipses.json           # parsed from NASA catalog
      lunar_eclipses.json
    conftest.py                     # shared fixtures and helpers
    test_solar_eclipses.py
    test_lunar_eclipses.py
  requirements.txt
```

## Angular Separation Formula

Use the Vincenty formula (numerically stable at all separations, including near-zero):

```python
def angular_separation(ra1, dec1, ra2, dec2):
    """Angular separation in radians. All inputs in radians."""
    dra = ra2 - ra1
    return np.arctan2(
        np.sqrt((np.cos(dec2) * np.sin(dra))**2 +
                (np.cos(dec1) * np.sin(dec2) - np.sin(dec1) * np.cos(dec2) * np.cos(dra))**2),
        np.sin(dec1) * np.sin(dec2) + np.cos(dec1) * np.cos(dec2) * np.cos(dra)
    )
```

The simpler `arccos` formula has floating-point domain errors at very small separations — exactly where eclipses occur. The Vincenty formula avoids this.

## Eclipse Testing

### Coordinate Frame

All `radec_direct` calls use `epoch='j2000'` explicitly. This puts coordinates in the ICRF frame. Example:

```python
system.move_system(julian_day)
ra, dec, dist = system['sun'].radec_direct(system['earth'], epoch='j2000', formatted=False)
```

Note: `move_system()` must be called before each position query — it accepts a single scalar Julian day (TT) and is not vectorized.

### Scan Approach

For each known eclipse, scan a +/-2 hour window around the NASA peak time. Use a two-pass approach:

1. **Coarse pass**: 5-minute steps (49 evaluations), find approximate minimum
2. **Fine pass**: 1-minute steps in a +/-10 minute window around the coarse minimum (21 evaluations)

Total: ~70 `move_system` calls per eclipse instead of 241. At ~1-5ms per call, testing 1000 eclipses takes roughly 1-6 minutes.

This decouples two questions:
1. **Does Tychos predict the right geometry?** (minimum separation below threshold)
2. **Does Tychos get the timing right?** (offset from known peak)

### Solar Eclipse Detection

1. Compute Sun and Moon RA/Dec from Tychos at each time step
2. Compute angular separation using Vincenty formula
3. Find the minimum separation in the window
4. Check if minimum < threshold

Angular diameter reference values:
- Sun: ~0.527 degrees mean (varies 0.524-0.542)
- Moon: ~0.518 degrees mean (varies 0.491-0.559)

Threshold for detection: separation < ~0.8 degrees (sum of mean angular radii + margin).

### Lunar Eclipse Detection

1. Compute the anti-solar point: `((ra_sun + pi) % (2*pi), -dec_sun)`
2. Compute Moon's angular distance from the anti-solar point
3. Find the minimum distance in the window
4. Check against thresholds:
   - Earth's umbral shadow radius at Moon's distance: ~0.45 degrees
   - Earth's penumbral shadow radius: ~1.25 degrees

Eclipse types:
- **Total lunar**: anti-solar separation < (R_umbra - R_moon)
- **Partial lunar**: anti-solar separation < (R_umbra + R_moon)
- **Penumbral**: anti-solar separation < (R_penumbra + R_moon)

### False Positive Checks

Test 5 non-eclipse new moons and 5 non-eclipse full moons (selected at least 1 month away from any catalog eclipse) and verify thresholds are NOT met.

### Outputs Per Eclipse

- Whether Tychos detects the eclipse (detected/not detected)
- Minimum angular separation achieved (arcminutes)
- Time offset between Tychos-predicted minimum and NASA peak time (minutes)
- Eclipse type agreement (total/annular/partial)

## Smoke Tests

Before running the full suite, two sanity checks:

1. **Verify TychosSystem returns expected values at a known date** — compare Sun and Moon RA/Dec at J2000 epoch against the values in the existing tychos_skyfield test suite
2. **Verify the angular separation formula** — test with known coordinate pairs (e.g., two points 90 degrees apart, two identical points, two antipodal points)

## Time Precision Notes

- Julian date `float64` precision is ~1 microsecond
- 1 minute = ~0.000694 Julian days
- Moon moves ~0.5 degrees/hour, so 1-minute scan steps give ~0.008 degree resolution
- Eclipse peak times from NASA are known to the minute
