# Methodology

[← Back to README](../README.md)

How Tychos eclipse predictions are scored against the NASA catalogs.

## Predicted Reference Geometry

[`server/services/predicted_geometry.py`](../server/services/predicted_geometry.py) turns each catalog record into the geometry that *should* hold at the moment of maximum eclipse, using only the published `gamma` and magnitude (no Skyfield, no Tychos):

- **Expected Sun-Moon (or Moon-to-shadow) separation** is derived from gamma — the perpendicular distance of the shadow axis from Earth's center, in Earth radii — by projecting it onto the celestial sphere at the mean Earth-Moon distance.
- **Solar disk radii** for central eclipses (total/annular/hybrid) come from the magnitude directly: `magnitude = D_moon / D_sun`, so `R_moon = magnitude × R_sun_mean`. Partial eclipses fall back to the mean lunar radius.
- **Lunar shadow radii** are inverted from umbral and penumbral magnitudes plus the gamma-derived Moon-to-shadow distance, recovering the umbral and penumbral radii implied by the catalog rather than treating them as constants.
- **Approach angle** is taken from the sign of gamma adjusted for the ecliptic tilt (~23.44°), so the predicted diagram shows the Moon entering from the geometrically correct side.

The result is precomputed at seed time into a `predicted_reference` table (one row per eclipse) and serves as the per-eclipse ground truth for both the Tychos and JPL pipelines.

## How Eclipse Detection Works

### Core Principle

An eclipse occurs when the Sun and Moon (or Moon and Earth's shadow) are very close together on the celestial sphere as seen from Earth. We compute the closest approach in each model and compare it to the catalog-derived expected separation.

### Solar Eclipse Detection

For each solar eclipse in the NASA catalog:

1. **Move the Tychos system** to the catalog's Julian Day (TT)
2. **Two-pass scan** around that time to find the minimum Sun-Moon angular separation:
   - **Coarse pass:** Step through a ±2 hour window in 5-minute increments
   - **Fine pass:** Step through ±10 minutes around the coarse minimum in 1-minute increments
3. **Compute angular separation** between the Tychos-predicted Sun and Moon positions using the [Vincenty formula](https://en.wikipedia.org/wiki/Great-circle_distance#Formulas) (numerically stable for both small and large angles)
4. **Record the minimum** as the model's predicted Sun-Moon separation for that eclipse, along with the timing offset from the catalog moment

### Lunar Eclipse Detection

For each lunar eclipse in the NASA catalog:

1. **Compute the anti-solar point** (Earth's shadow center): RA = Sun RA + π, Dec = −Sun Dec
2. **Two-pass scan** (same coarse/fine strategy) to minimize the Moon-to-antisolar-point separation
3. **Record the minimum** as the model's predicted Moon-to-shadow separation

**Why separation-based detection works:** Eclipse geometry is fundamentally about angular proximity on the celestial sphere. A solar eclipse requires the Moon to transit across the solar disk (small Sun-Moon separation). A lunar eclipse requires the Moon to enter Earth's shadow cone, which projects to a roughly circular region opposite the Sun. By measuring angular separation, we reduce a complex 3D alignment problem to a single scalar that directly corresponds to the physical eclipse condition. This is the same basic approach used by professional eclipse prediction codes, though they additionally account for parallax, limb corrections, and exact shadow geometry.

### What the Two-Pass Scan Accounts For

The NASA catalog provides eclipse times in Terrestrial Time, but the Tychos model may have small timing offsets in when it predicts closest approach. The scan window (±2 hours coarse, ±10 minutes fine) accommodates timing differences while the `timing_offset_min` field records exactly how far off the model's best alignment is from the catalog time. This offset itself is a useful accuracy metric.

## Error Metrics

Eclipse results are scored as continuous angular errors against the catalog-derived predicted reference. There are no thresholds and no pass/fail buckets — every result is just a number in arcminutes.

For each eclipse, the worker records:

- **`tychos_error_arcmin`** — `|tychos_separation − predicted_separation|`, in arcminutes. How far off the Tychos-model closest approach is from the geometry implied by the catalog's gamma/magnitude.
- **`jpl_error_arcmin`** — the same comparison computed from the JPL DE440s ephemeris at the catalog moment. This calibrates how well the *standard* heliocentric model matches the catalog reference, and serves as a floor for what "good" looks like.
- **`timing_offset_min`** — how far the Tychos minimum-separation moment sits from the catalog time.

The dashboard surfaces these as **mean tychos error** and **mean jpl error** at the run, dataset, and Saros-series level, with filterable error ranges in the results table.

### Why Compare Against a Catalog-Derived Reference?

The earlier version of this project used a hand-picked Sun-Moon separation threshold and a "JPL rescue" rule that flipped near-misses to pass. Both were arbitrary cutoffs on what is fundamentally a continuous quantity, and they obscured the actual size of the disagreement. Scoring directly against a geometry derived from the catalog's own gamma and magnitude removes the cutoffs, makes the metric monotonic with model accuracy, and lets us compare Tychos and JPL on identical footing — JPL is no longer the reference, it's another contestant being measured against the same catalog truth.
