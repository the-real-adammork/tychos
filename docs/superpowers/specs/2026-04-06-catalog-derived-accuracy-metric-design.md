# Catalog-Derived Accuracy Metric

Replace the arbitrary fixed-threshold eclipse detection system with continuous accuracy measurement derived from NASA catalog parameters.

## Problem

The current system uses a fixed angular separation threshold (0.8° for solar, type-dependent for lunar) to decide pass/fail, with a secondary "JPL rescue" mechanism for near-misses. This is arbitrary — the threshold doesn't account for how central or grazing each eclipse is, and the pass/fail binary discards useful information about model accuracy. The NASA catalog provides enough geometric parameters (gamma, magnitude, shadow magnitudes) to compute what the actual Sun-Moon geometry should look like for each eclipse, enabling a proper accuracy measurement.

## Approach

Compute the **expected eclipse geometry** from catalog parameters alone (no JPL, no Tychos). Store this as a precomputed reference table. Measure both Tychos and JPL against this prediction. Report continuous error values instead of pass/fail.

Three diagrams per eclipse: Predicted (catalog-derived), Tychos, JPL. JPL serves as a sanity check — if JPL's error relative to the predicted geometry is consistently near-zero, the catalog derivation is sound. If JPL shows significant error, the derivation needs investigation.

No pass/fail threshold is defined in this spec. Continuous error values are shipped first; thresholds will be defined later after analyzing the error distribution across all eclipses.

## Design

### 1. Predicted Reference Table

New table `predicted_reference`, seeded once from catalog JSON files. One row per eclipse, keyed by `julian_day_tt` + `test_type`.

**Schema:**

```sql
CREATE TABLE predicted_reference (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    julian_day_tt REAL NOT NULL,
    test_type TEXT NOT NULL,
    expected_separation_arcmin REAL NOT NULL,
    moon_apparent_radius_arcmin REAL NOT NULL,
    sun_apparent_radius_arcmin REAL,          -- solar only
    umbra_radius_arcmin REAL,                 -- lunar only
    penumbra_radius_arcmin REAL,              -- lunar only
    approach_angle_deg REAL,                  -- Moon position angle relative to center
    gamma REAL NOT NULL,
    catalog_magnitude REAL NOT NULL,
    UNIQUE(julian_day_tt, test_type)
);
```

**Derivation formulas (solar eclipses):**

- Expected separation: `sep ≈ arctan(|gamma| × R_earth / D_moon)` converted to arcminutes. `R_earth` = 6371 km, `D_moon` ≈ 384400 km (mean). Note: Moon distance varies ~356k–407k km across its orbit. Using the mean introduces up to ~7% error in the expected separation. A future refinement could derive actual Moon distance from the catalog magnitude ratio for central eclipses.
- Moon/Sun size ratio: For central eclipses, `magnitude = D_moon / D_sun`, so `R_moon = magnitude × R_sun`. Combined with the known mean Sun apparent radius (~16'), solve for both.
- Approach angle: Gamma sign (positive = north, negative = south of Earth center) combined with the ecliptic position angle at the Sun's RA/Dec for that date. The Moon approaches roughly along the ecliptic plane.

**Derivation formulas (lunar eclipses):**

- Expected separation: Same gamma-based formula as solar.
- Moon apparent radius: Derived from the relationship between `pen_mag`, `um_mag`, and shadow geometry. The ratio of penumbral to umbral magnitude constrains the Moon's apparent size relative to the shadow radii.
- Umbral radius: From `um_mag` immersion geometry — `R_umbra = um_mag × D_moon / 2 + distance - R_moon`, where distance is the Moon-to-shadow-center separation from gamma.
- Penumbral radius: Same approach using `pen_mag`.
- Approach angle: Same as solar, using gamma sign + ecliptic geometry.

**Seed function:** New `_seed_predicted_reference()` in `seed.py`. Reads catalog JSON, computes all derived values using pure geometry (no Skyfield, no Tychos). Called alongside existing `_seed_jpl_reference()`.

### 2. Schema Changes to eclipse_results

Add two columns:

```sql
ALTER TABLE eclipse_results ADD COLUMN tychos_error_arcmin REAL;
ALTER TABLE eclipse_results ADD COLUMN jpl_error_arcmin REAL;
```

The `detected` column remains in the schema but is no longer used for status computation. All status/rescue logic is removed.

### 3. Fresh Database

Drop and recreate all data tables (`eclipse_results`, `runs`, reference tables). Seed repopulates `jpl_reference` and `predicted_reference`. Existing parameter sets get fresh runs queued automatically.

This avoids any backfill or backward-compatibility complexity. No existing data is worth preserving.

### 4. Worker Changes

After the scanner produces Tychos results for each eclipse:

1. Load `predicted_reference` rows for the test type
2. For each eclipse result: `tychos_error_arcmin = |tychos_separation - expected_separation|`
3. Load `jpl_reference` rows for the test type
4. For each eclipse result: compute JPL separation from `jpl_reference` positions, then `jpl_error_arcmin = |jpl_separation - expected_separation|`
5. Store both error values in `eclipse_results`

### 5. Results API Changes

**`results_routes.py`:**

Remove:
- `_compute_status()` function
- `_enrich()` function (status/jpl_rescued computation)
- `JPL_CLOSE_THRESHOLD` constant
- Status-based filter logic (pass/fail/threshold_pass/threshold_fail)

Add:
- Error values served directly from `eclipse_results`
- Stats endpoint returns: mean/median/max error for both Tychos and JPL, broken down by eclipse type
- Filter by error range (e.g. `min_error=30` to show eclipses with Tychos error > 30')

### 6. Three-Diagram Detail Page

**ResultDetailPage.tsx** — three diagrams side by side:

**Predicted (Catalog)**
- Center: Sun (solar) or shadow center (lunar)
- Moon placed at `expected_separation_arcmin` from center, at `approach_angle_deg`
- Disk sizes from `predicted_reference` (not constants): `moon_apparent_radius_arcmin`, `sun_apparent_radius_arcmin` (solar), `umbra_radius_arcmin` + `penumbra_radius_arcmin` (lunar)
- No velocity arrow (catalog doesn't provide velocity)
- Label: "Predicted (Catalog)"

**Tychos**
- Same as current eclipse diagram, but disk sizes from `predicted_reference` instead of constants (fair comparison across all three diagrams)
- Velocity arrow stays
- Error annotation: `tychos_error_arcmin`
- Label: "Tychos"

**JPL (DE440s)**
- Same as current, disk sizes from `predicted_reference`
- Velocity arrow stays
- Error annotation: `jpl_error_arcmin`
- Label: "JPL (DE440s)"

All three diagrams use the same scale and viewport extent. Separation line in each shows that diagram's separation value.

**Measurements card** below diagrams: three columns (Predicted, Tychos, JPL) each showing separation and positions. Bottom section shows error for each model. No pass/fail badges.

### 7. Results Table Changes

**ResultsTable.tsx** — new columns:

| Column | Source |
|---|---|
| Date | Unchanged |
| Type | Unchanged |
| Magnitude | Unchanged |
| Expected Sep | `predicted_reference.expected_separation_arcmin` |
| Tychos Sep | `eclipse_results.min_separation_arcmin` |
| Tychos Error | `eclipse_results.tychos_error_arcmin` |
| JPL Sep | `jpl_reference.separation_arcmin` |
| JPL Error | `eclipse_results.jpl_error_arcmin` |
| Timing Offset | Unchanged |

Removed: Threshold badge, JPL Check badge, Status badge.

**Stats bar** replaced with error distribution summary:
- Mean / Median / Max Tychos error
- Mean / Median / Max JPL error
- Breakdown by eclipse type

**Filters**: replace status filter (pass/fail/rescued) with error range filter.

### 8. Other Affected Pages

All pages that reference pass/fail/rescued metrics need updating:

- **RunTable** (`run-table.tsx`) — replace detected/total counts and pass rates with mean/median error per run
- **DashboardPage** — `stats-cards.tsx`: replace pass/fail aggregates with error metrics. `leaderboard.tsx`: rank parameter sets by mean error instead of pass rate. `recent-runs.tsx`: show error summaries instead of detection counts
- **ComparePage** / **ChangedEclipses** (`changed-eclipses.tsx`) — replace "NEW DETECT" / "LOST" badges with error deltas ("error improved by X'" / "error worsened by X'")
- **ParamDetailPage** / **ParamVersionDetailPage** — replace pass rate summaries with error summaries

### 9. Removals

Code that gets deleted or gutted:

- `helpers.py`: `SOLAR_DETECTION_THRESHOLD`, `LUNAR_UMBRAL_RADIUS`, `LUNAR_PENUMBRAL_RADIUS`, `MOON_MEAN_ANGULAR_RADIUS` constants, `lunar_threshold()` function
- `results_routes.py`: `_compute_status()`, `_enrich()`, `JPL_CLOSE_THRESHOLD`, status filter branches
- `results-table.tsx`: `StatsBar` component (replaced), status badges, status filter options
- `ResultDetailPage.tsx`: status/threshold/rescued badge rendering, two-diagram layout (replaced with three)
- `changed-eclipses.tsx`: "NEW DETECT" / "LOST" badge logic
- `run_eclipses.py`: threshold-based detection counting (the standalone CLI runner — update to report errors)
- `test_smoke.py`: `TestFalsePositives` class relies on threshold detection — rework to validate error computation

## Out of Scope

- No pass/fail threshold defined — continuous error values first, thresholds from data later
- No changes to the Tychos model or two-pass scanner logic
- No changes to JPL reference computation (Skyfield + DE440s stays the same)
- No new celestial event types — solar and lunar eclipses only
- No parameter optimization — this work enables it by providing a continuous metric
