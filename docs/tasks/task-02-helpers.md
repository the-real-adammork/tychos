# Task 02: Angular Separation Helpers

**Plan:** test-plan.md
**Prerequisites:** task-01

## Objective

Implement the shared utility functions used by all eclipse tests: the Vincenty angular separation formula and the two-pass eclipse scan logic.

## Steps

### 1. Create tests/helpers.py

Contains:

**`angular_separation(ra1, dec1, ra2, dec2)`**
- Vincenty formula, all inputs/output in radians
- Must handle identical points (separation = 0) without NaN

**`scan_min_separation(system, body1, body2, center_jd, half_window_hours=2)`**
- Two-pass scan around `center_jd`:
  - Coarse: 5-minute steps over +/-`half_window_hours`
  - Fine: 1-minute steps in +/-10 minutes around coarse minimum
- At each step: call `system.move_system(jd)`, get RA/Dec for both bodies via `radec_direct(system['earth'], epoch='j2000', formatted=False)`
- Returns: `(min_separation_rad, best_jd)` — the minimum angular separation found and the Julian day it occurred at

**`scan_lunar_eclipse(system, center_jd, half_window_hours=2)`**
- Same two-pass scan, but computes Moon's distance from the anti-solar point
- Anti-solar point: `((ra_sun + pi) % (2*pi), -dec_sun)`
- Returns: `(min_separation_rad, best_jd)`

### 2. Constants

In `tests/helpers.py` or a separate `tests/constants.py`:

```python
SOLAR_DETECTION_THRESHOLD = 0.8 * (pi / 180)   # 0.8 degrees in radians
LUNAR_UMBRAL_RADIUS = 0.45 * (pi / 180)         # degrees -> radians
LUNAR_PENUMBRAL_RADIUS = 1.25 * (pi / 180)
MOON_MEAN_ANGULAR_RADIUS = 0.259 * (pi / 180)
MINUTE_IN_DAYS = 1.0 / 1440.0
```

## Verification

- [ ] `angular_separation(0, 0, pi/2, 0)` returns `pi/2` (90 degrees)
- [ ] `angular_separation(x, y, x, y)` returns 0 for any x, y
- [ ] `angular_separation(0, 0, pi, 0)` returns `pi` (180 degrees)
- [ ] `scan_min_separation` returns a result within the scan window
- [ ] All functions have no skyfield dependency — only numpy and tychos_skyfield.baselib
