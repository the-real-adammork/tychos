# Task 04: Solar Eclipse Tests

**Plan:** test-plan.md
**Prerequisites:** task-02, task-03

## Objective

For every solar eclipse in the NASA catalog, run the Tychos model and report whether it predicts the eclipse, the minimum Sun-Moon separation, and the timing offset.

## Steps

### 1. Create tests/test_solar_eclipses.py

Load `tests/data/solar_eclipses.json`. For each eclipse:

1. Create a `TychosSystem` (or reuse one)
2. Call `scan_min_separation(system, 'sun', 'moon', eclipse['julian_day_tt'])`
3. Record:
   - `detected`: whether `min_separation < SOLAR_DETECTION_THRESHOLD`
   - `min_separation_arcmin`: minimum separation in arcminutes
   - `timing_offset_min`: `(best_jd - eclipse['julian_day_tt']) * 1440` (in minutes)
   - `catalog_type`: the NASA catalog's eclipse type
4. Write results to stdout or a results file

### 2. Structure as pytest

Use `pytest.mark.parametrize` over the eclipse list so each eclipse is a separate test case. Each test reports data via print or a shared results collector rather than asserting pass/fail.

Alternatively, structure as a single test that iterates all eclipses and writes a summary CSV:

```
date,catalog_type,detected,min_separation_arcmin,timing_offset_min
2000-01-01T12:00:00,total,yes,2.3,4.2
```

### 3. Summary output

After all eclipses are tested, print:
- Total eclipses tested
- Number detected / not detected
- Detection rate by eclipse type (total, annular, partial)
- Mean and max timing offset for detected eclipses

## Verification

- [ ] Test runs to completion without errors
- [ ] Results CSV/output is generated
- [ ] At least a few well-known recent eclipses (e.g., 2017-08-21 total solar) show as detected
