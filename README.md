# Tychos Eclipse Prediction Test Suite

This project tests the [Tychos model](https://www.tychos.space/)'s ability to predict historical solar and lunar eclipses. It computes Sun and Moon positions using the Tychos geometric model, compares them against NASA's authoritative eclipse catalogs, and cross-references results with JPL ephemeris data to evaluate model accuracy.

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Dependencies](#dependencies)
- [Datasets](#datasets)
- [How Eclipse Detection Works](#how-eclipse-detection-works)
- [JPL Rescue: Recovering Threshold Failures](#jpl-rescue-recovering-threshold-failures)
- [Visualizations](#visualizations)
- [Admin Dashboard](#admin-dashboard)
- [Running the Tests](#running-the-tests)
- [Open Questions](#open-questions)

---

## Architecture Overview

```
┌────────────────────┐      ┌──────────────────────┐
│  NASA Eclipse       │      │  tychos_skyfield      │
│  Catalogs (HTML)    │      │  (Python model)       │
│  parse_nasa_      │      │  baselib.py            │
│    eclipses.py     │──▶   │  skyfieldlib.py        │
│  ──▶ JSON catalogs │      └──────────┬───────────┘
└────────────────────┘                 │
                                       ▼
                          ┌──────────────────────────┐
                          │  Eclipse Scanner          │
                          │  tests/helpers.py         │
                          │  server/services/         │
                          │    scanner.py             │
                          └──────────┬───────────────┘
                                     │
                    ┌────────────────┼────────────────┐
                    ▼                                  ▼
          ┌──────────────┐                  ┌──────────────────┐
          │  SQLite DB    │                  │  JPL Reference    │
          │  Results +    │◀─── compare ───▶│  (Skyfield +      │
          │  Runs         │                  │   DE440s.bsp)     │
          └──────┬───────┘                  └──────────────────┘
                 │
                 ▼
          ┌──────────────┐
          │  Admin UI     │
          │  (React SPA)  │
          └──────────────┘
```

---

## Dependencies

### tychos_skyfield (Submodule)

The core Tychos model implementation in Python. Included as a git submodule at `tychos_skyfield/`.

- **`baselib.py`** — The complete Tychos solar system model. Implements `TychosSystem`, which positions all planets (Sun, Moon, Mercury through Neptune, and several minor bodies) using the Tychos geometric model with deferent/epicycle-style orbital mechanics. Computes RA/Dec in the ICRF/J2000 frame. Orbital parameters are loaded from `orbital_params.json`, which is synced from the TSN (Tychosium) JavaScript 3D simulator's `celestial-settings.json`.

- **`skyfieldlib.py`** — An adapter that wraps Tychos objects as [Skyfield](https://rhodesmill.org/skyfield/) `VectorFunction` objects, allowing Tychos-computed positions to be used interchangeably with JPL ephemeris data within the Skyfield API. This enables direct RA/Dec comparisons between Tychos and the standard (heliocentric) model.

**Source:** Private submodule (contact the Tychos project for access)

### Skyfield

[Skyfield](https://rhodesmill.org/skyfield/) is a Python library for positional astronomy by Brandon Rhodes. It computes positions of stars, planets, and satellites using high-accuracy numerical data from NASA's Jet Propulsion Laboratory (JPL).

- **Used for:** Computing JPL reference positions of the Sun and Moon at each catalog eclipse time, serving as the "standard model" baseline for comparison.
- **Ephemeris file:** [`de440s.bsp`](https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/) — The compact version of JPL's DE440 planetary ephemeris, covering 1849–2150 CE.
- **Reference:** [rhodesmill.org/skyfield](https://rhodesmill.org/skyfield/)
- **PyPI:** [skyfield](https://pypi.org/project/skyfield/)

### NumPy

Used throughout for trigonometric calculations (angular separation, coordinate transforms) and array operations.

- **Reference:** [numpy.org](https://numpy.org/)

### SciPy

Used in `baselib.py` for `scipy.spatial.transform.Rotation` — 3D rotation algebra for orbit tilts, coordinate frame transformations, and RA/Dec computation from Cartesian positions.

- **Reference:** [scipy.org](https://www.scipy.org/)

### FastAPI + aiosqlite

The admin server uses [FastAPI](https://fastapi.tiangolo.com/) for the API layer and [aiosqlite](https://pypi.org/project/aiosqlite/) for async SQLite access. Results are stored in `results/tychos_results.db`.

---

## Datasets

### NASA Five Millennium Canon of Eclipse Catalogs

The ground truth for eclipse occurrence comes from NASA's Goddard Space Flight Center eclipse catalogs compiled by Fred Espenak and Jean Meeus. These are the canonical reference catalogs used by the astronomy community.

**Solar eclipses (1901–2100):**
- [SE1901-2000.html](https://eclipse.gsfc.nasa.gov/SEcat5/SE1901-2000.html)
- [SE2001-2100.html](https://eclipse.gsfc.nasa.gov/SEcat5/SE2001-2100.html)

**Lunar eclipses (1901–2100):**
- [LE1901-2000.html](https://eclipse.gsfc.nasa.gov/LEcat5/LE1901-2000.html)
- [LE2001-2100.html](https://eclipse.gsfc.nasa.gov/LEcat5/LE2001-2100.html)

**Reference:** Espenak, F. and Meeus, J., [Five Millennium Canon of Solar Eclipses: -1999 to +3000](https://eclipse.gsfc.nasa.gov/SEpubs/5MCSE.html), NASA/TP-2006-214141

The script `scripts/parse_nasa_eclipses.py` fetches these HTML pages, extracts the fixed-width tabular data from `<pre>` blocks, parses each record's date/time, eclipse type, and magnitude, converts the timestamp to Julian Day (Terrestrial Time), and writes the result to `tests/data/solar_eclipses.json` and `tests/data/lunar_eclipses.json`.

Each record contains:
- `julian_day_tt` — Julian Day in Terrestrial Time (TT), the time scale used by the catalog
- `date` — ISO 8601 date/time string
- `type` — Normalized eclipse type (`total`, `annular`, `partial`, `hybrid`, `penumbral`)
- `magnitude` — Eclipse magnitude from the catalog

### JPL DE440s Planetary Ephemeris

For each catalog eclipse, we compute the Sun and Moon positions as predicted by the standard heliocentric model using JPL's DE440 ephemeris via Skyfield. This provides an independent "where should the Sun and Moon actually be?" reference.

- **File:** `de440s.bsp` (compact version, auto-downloaded by Skyfield on first use)
- **Coverage:** 1849–2150 CE
- **Accuracy:** Sub-arcsecond for inner solar system bodies
- **Reference:** Park, R.S., et al., [The JPL Planetary and Lunar Ephemerides DE440 and DE441](https://doi.org/10.3847/1538-3881/abd414), The Astronomical Journal, 2021

The JPL data is precomputed at seed time (`server/seed.py`) and stored in the `jpl_reference` table, including Sun RA/Dec, Moon RA/Dec, Moon RA/Dec velocity, and angular separation — all computed at each catalog eclipse's Julian Day using Skyfield's `earth.at(t).observe()` method in the ICRF/J2000 frame.

---

## How Eclipse Detection Works

### Core Principle

An eclipse occurs when the Sun and Moon (or Moon and Earth's shadow) are very close together on the celestial sphere as seen from Earth. We test whether the Tychos model places them close enough at the right time.

### Solar Eclipse Detection

For each solar eclipse in the NASA catalog:

1. **Move the Tychos system** to the catalog's Julian Day (TT)
2. **Two-pass scan** around that time to find the minimum Sun-Moon angular separation:
   - **Coarse pass:** Step through a ±2 hour window in 5-minute increments
   - **Fine pass:** Step through ±10 minutes around the coarse minimum in 1-minute increments
3. **Compute angular separation** between the Tychos-predicted Sun and Moon positions using the [Vincenty formula](https://en.wikipedia.org/wiki/Great-circle_distance#Formulas) (numerically stable for both small and large angles)
4. **Compare to threshold:** If the minimum separation < **0.8°** (48 arcminutes), the eclipse is **detected**

**Why 0.8° is a good threshold:** The Sun's angular diameter is ~0.53° and the Moon's is ~0.52°. For a solar eclipse to occur, the Moon must pass within roughly one solar radius of the Sun's center. Our 0.8° threshold is intentionally generous — about 1.5× the sum of the mean angular radii — to account for timing uncertainty in the model while remaining selective enough to reject non-eclipse new moons (which typically have separations of several degrees). The `TestFalsePositives` test class verifies this selectivity.

### Lunar Eclipse Detection

For each lunar eclipse in the NASA catalog:

1. **Compute the anti-solar point** (Earth's shadow center): RA = Sun RA + π, Dec = −Sun Dec
2. **Two-pass scan** (same coarse/fine strategy) to minimize the Moon-to-antisolar-point separation
3. **Compare to type-dependent threshold:**
   - **Total/Partial eclipses:** Umbral radius (0.45°) + Moon radius (0.259°) = **0.709°** (42.5 arcmin)
   - **Penumbral eclipses:** Penumbral radius (1.25°) + Moon radius (0.259°) = **1.509°** (90.5 arcmin)

**Why separation-based detection works:** Eclipse geometry is fundamentally about angular proximity on the celestial sphere. A solar eclipse requires the Moon to transit across the solar disk (small Sun-Moon separation). A lunar eclipse requires the Moon to enter Earth's shadow cone, which projects to a roughly circular region opposite the Sun. By measuring angular separation, we reduce a complex 3D alignment problem to a single scalar that directly corresponds to the physical eclipse condition. This is the same basic approach used by professional eclipse prediction codes, though they additionally account for parallax, limb corrections, and exact shadow geometry.

### What the Two-Pass Scan Accounts For

The NASA catalog provides eclipse times in Terrestrial Time, but the Tychos model may have small timing offsets in when it predicts closest approach. The scan window (±2 hours coarse, ±10 minutes fine) accommodates timing differences while the `timing_offset_min` field records exactly how far off the model's best alignment is from the catalog time. This offset itself is a useful accuracy metric.

---

## JPL Rescue: Recovering Threshold Failures

Not all eclipses that fail the angular separation threshold represent genuine model failures. The "JPL rescue" mechanism distinguishes between:

1. **The Moon is in approximately the right place, but not quite close enough** — the Tychos model has the Moon near where JPL says it should be, and the threshold miss is due to small positional errors.

2. **The Moon is fundamentally in the wrong position** — a genuine prediction failure.

### How It Works

For every eclipse that **fails** the threshold test (separation too large):

1. **Compare the Tychos Moon position to the JPL Moon position** at the same Julian Day
2. **Compute `moon_error_arcmin`**: the angular separation between where Tychos places the Moon and where JPL/DE440 says it actually is
3. **If `moon_error_arcmin` < 60 arcminutes** (1°): the eclipse is **"JPL rescued"** and marked as **pass**
4. **If ≥ 60 arcminutes**: the eclipse remains **fail**

### Why This Makes Sense

If the Tychos Moon position is within 1° of the JPL Moon position, the model has the Moon in roughly the right part of the sky — the threshold failure is a near-miss caused by small accumulated errors in the geometric model, not a fundamental misplacement. The eclipse "would have been detected" with slightly better parameters. This is analogous to how observational astronomers distinguish between systematic errors and random noise.

### Status Categories

Each eclipse result has three possible states:

| Threshold | JPL Check | Final Status |
|-----------|-----------|-------------|
| **Pass** (sep < threshold) | Not checked | **Pass** (green) |
| **Fail** (sep ≥ threshold) | Moon error < 60' | **Pass** — JPL Rescued (blue) |
| **Fail** (sep ≥ threshold) | Moon error ≥ 60' or unknown | **Fail** (red) |

---

## Visualizations

The admin dashboard provides two types of eclipse geometry diagrams for each individual result, rendered as inline SVGs.

### Eclipse Geometry Diagram (per-result detail page)

Each eclipse result page shows two side-by-side diagrams: **Tychos** (left) and **JPL** (right).

**Solar eclipses** are centered on the Sun:
- A yellow circle represents the Sun's disk (16 arcminute radius)
- A gray circle represents the Moon's disk (15.55 arcminute radius)
- A dashed yellow circle shows the detection threshold (48 arcminute radius)
- A dashed red line connects Sun center to Moon center with the separation labeled
- An arrow on the Moon shows its velocity direction (RA/Dec velocity extrapolated over 3 hours)
- Grid lines at 10-arcminute intervals provide scale

**Lunar eclipses** are centered on the anti-solar point (Earth's shadow):
- A dark gray filled circle represents the umbral shadow (42 arcminute radius)
- A lighter gray circle represents the penumbral shadow (78 arcminute radius)
- The Moon disk, threshold, separation line, and velocity arrow are drawn identically

The JPL diagram uses positions computed from `de440s.bsp` via Skyfield, providing a direct geometric comparison of where each model places the bodies relative to the eclipse condition.

### Sky Position Diagram

A full-sky Mollweide-style RA/Dec plot showing:
- Sun and Moon positions on the celestial sphere (RA 0–24h, Dec ±90°)
- An approximate ecliptic curve (sinusoidal with 23.44° obliquity)
- The celestial equator
- A connecting line between Sun and Moon

---

## Admin Dashboard

The web-based admin interface (`admin/` + `server/`) provides:

- **Parameter management** — Create, edit, version, and fork orbital parameter sets
- **Run management** — Queue eclipse test runs against any parameter version; a background worker executes them
- **Results browsing** — Paginated tables with filtering by eclipse type and pass/fail status
- **Stats bar** — Visual breakdown: threshold pass (green), JPL rescued (blue), fail (red)
- **Comparison view** — Side-by-side diff of two parameter versions showing which eclipses changed detection status
- **Per-result detail** — Full geometry diagrams, position readouts, and JPL comparison for each eclipse

---

## Running the Tests

### Prerequisites

```bash
pip install numpy scipy skyfield
```

### Standalone CLI (original test runner)

```bash
# Run all parameter sets
python tests/run_eclipses.py

# Run a specific parameter set
python tests/run_eclipses.py params/v1-original.json

# Force re-run
python tests/run_eclipses.py --force
```

### Unit tests

```bash
pytest tests/test_smoke.py -v
```

### Regenerate eclipse catalogs from NASA

```bash
python scripts/parse_nasa_eclipses.py
```

### Admin server

```bash
# Set credentials
export TYCHOS_ADMIN_USER=admin@tychos.local
export TYCHOS_ADMIN_PASSWORD=your_password

# Start the server (runs migrations, seeds JPL data on first launch)
python -m server.app
```

---

## Open Questions

### Accuracy and Calibration

1. **Threshold sensitivity.** The solar detection threshold (0.8°) and JPL rescue threshold (60 arcminutes) were chosen empirically. A systematic study of the separation distribution for known eclipses vs. non-eclipse new/full moons would establish whether tighter thresholds are justified, and whether the current thresholds introduce false positives or false negatives.

2. **Timing offset distribution.** The timing offsets recorded for detected eclipses (how many minutes the Tychos minimum-separation moment differs from the catalog time) have not been rigorously analyzed for systematic bias. A consistent positive or negative offset could indicate a drift in the model's time calibration.

3. **Lunar eclipse shadow geometry.** The umbral and penumbral shadow radii (0.45° and 1.25°) are approximated as constants. In reality, shadow size varies with Earth-Moon distance. Using constant radii may cause marginal penumbral eclipses at lunar apogee to be treated differently than at perigee.

### Dependencies and Data Integrity

4. **DE440s vs. DE421.** The JPL reference data uses `de440s.bsp` (DE440, 2021), while `skyfieldlib.py` examples reference `de421.bsp` (DE421, 2008). DE440 incorporates more recent data and is more accurate, but this means the Skyfield adapter examples and the test infrastructure use different ephemeris versions. It has not been verified whether this difference is material for Sun/Moon positions in the 1901–2100 range.

5. **TT vs. UTC ambiguity.** The NASA catalogs provide times in Terrestrial Time (TT). The `baselib.py` Julian Day reference epoch comment says "2000-6-21 12:00:00" without specifying the time scale. The `skyfieldlib.py` adapter passes `t.tt` (Terrestrial Time) to `move_system()`, which appears correct, but the chain from catalog → JSON → Tychos model should be audited to confirm no ΔT correction is being double-applied or dropped.

6. **Vincenty formula edge cases.** The angular separation uses the Vincenty formula, which is well-behaved for small angles (unlike the cosine formula). However, the implementation has not been tested against a reference implementation for edge cases near the poles or at exactly 0°/180° separation beyond the basic smoke tests.

### Model Questions

7. **J2000 quaternion hardcoding.** The `baselib.py` RA/Dec calculation uses a hardcoded quaternion (`[-0.1420..., 0.6927..., -0.1451..., 0.6919...]`) for the J2000 epoch frame transformation. The code comments state this was "obtained by manually getting rotation quaternion of polar axis for the date 2000/01/01 12:00." The derivation of this quaternion and its sensitivity to the polar axis model parameters have not been independently verified.

8. **Moon velocity computation.** Moon RA/Dec velocities are computed as a simple finite difference over 1 hour (`jd + 1/24`). For the velocity arrows in the visualization this is fine, but if velocities are ever used for interpolation or refined scanning, the 1-hour step may be too coarse near eclipse mid-point where the Moon's apparent motion can change direction.

9. **Parameter sensitivity.** The system supports multiple parameter sets, but the relationship between individual orbital parameters (orbit radius, tilt, speed, center offsets) and eclipse detection accuracy has not been systematically mapped. Small changes to Moon deferent parameters likely dominate eclipse detection, but this hasn't been quantified.
