# Task 06: Smoke and False-Positive Tests

**Plan:** test-plan.md
**Prerequisites:** task-02

## Objective

Sanity-check the test infrastructure and verify that the detection thresholds don't produce false positives on non-eclipse dates.

## Steps

### 1. Smoke tests in tests/test_smoke.py

**Angular separation formula verification:**
- Two identical points → separation = 0
- Points 90 degrees apart → separation = pi/2
- Antipodal points → separation = pi
- Near-zero separation (0.001 radians apart) → stable result, no NaN

**TychosSystem sanity check:**
- Create system at default time (JD 2451717.0 = 2000-06-21 12:00:00 TT)
- Verify Sun and Moon RA/Dec are in a reasonable range (not NaN, not zero)
- Cross-check against the values in tychos_skyfield's existing test_base_position.py

### 2. False positive tests in tests/test_false_positives.py

Select 5 new moon dates and 5 full moon dates that are NOT eclipses (at least 1 month from any catalog eclipse). For each:

**Solar false positive (new moon dates):**
- Run `scan_min_separation` for Sun-Moon
- Assert separation stays ABOVE `SOLAR_DETECTION_THRESHOLD`

**Lunar false positive (full moon dates):**
- Run `scan_lunar_eclipse`
- Assert Moon-to-antisolar distance stays ABOVE penumbral threshold

Hardcode the 10 dates directly in the test file — no external data needed.

## Verification

- [ ] All smoke tests pass
- [ ] All false positive tests pass (no eclipses detected on non-eclipse dates)
- [ ] `pytest tests/test_smoke.py tests/test_false_positives.py -v` all green
