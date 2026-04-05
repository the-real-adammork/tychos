# Task 05: Lunar Eclipse Tests

**Plan:** test-plan.md
**Prerequisites:** task-02, task-03

## Objective

For every lunar eclipse in the NASA catalog, run the Tychos model and report whether it predicts the eclipse, the minimum Moon-to-antisolar separation, and the timing offset.

## Steps

### 1. Create tests/test_lunar_eclipses.py

Load `tests/data/lunar_eclipses.json`. For each eclipse:

1. Call `scan_lunar_eclipse(system, eclipse['julian_day_tt'])`
2. Record:
   - `detected`: whether min separation falls within the appropriate threshold for the catalog type (penumbral uses `LUNAR_PENUMBRAL_RADIUS + MOON_MEAN_ANGULAR_RADIUS`, partial/total uses `LUNAR_UMBRAL_RADIUS + MOON_MEAN_ANGULAR_RADIUS`)
   - `min_separation_arcmin`: minimum Moon-to-antisolar distance in arcminutes
   - `timing_offset_min`: offset from catalog peak in minutes
   - `catalog_type`: NASA catalog's eclipse type (total, partial, penumbral)
3. Write results to stdout or a results CSV

### 2. Summary output

After all eclipses are tested, print:
- Total eclipses tested
- Number detected / not detected
- Detection rate by eclipse type (total, partial, penumbral)
- Mean and max timing offset for detected eclipses

## Verification

- [ ] Test runs to completion without errors
- [ ] Results CSV/output is generated
- [ ] A few well-known recent lunar eclipses show as detected
