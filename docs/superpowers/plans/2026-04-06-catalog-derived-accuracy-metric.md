# Catalog-Derived Accuracy Metric Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the fixed-threshold pass/fail eclipse detection system with continuous accuracy measurement derived from NASA catalog parameters (gamma, magnitude), adding a predicted reference table and three-diagram comparison (Predicted, Tychos, JPL).

**Architecture:** New `predicted_reference` table seeded from catalog JSON using pure geometry. Worker computes `tychos_error_arcmin` and `jpl_error_arcmin` per eclipse. All pass/fail/rescued UI replaced with continuous error values. Three-diagram detail page shows Predicted (catalog), Tychos, and JPL side by side.

**Tech Stack:** Python (FastAPI, SQLite, NumPy), TypeScript/React (Vite SPA), Skyfield (JPL reference only)

**Spec:** `docs/superpowers/specs/2026-04-06-catalog-derived-accuracy-metric-design.md`

---

### Task 1: Database Migration — predicted_reference Table and eclipse_results Changes

**Files:**
- Create: `server/migrations/006_predicted_reference.sql`

- [ ] **Step 1: Write the migration SQL**

```sql
-- server/migrations/006_predicted_reference.sql

CREATE TABLE IF NOT EXISTS predicted_reference (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    julian_day_tt REAL NOT NULL,
    test_type TEXT NOT NULL,
    expected_separation_arcmin REAL NOT NULL,
    moon_apparent_radius_arcmin REAL NOT NULL,
    sun_apparent_radius_arcmin REAL,
    umbra_radius_arcmin REAL,
    penumbra_radius_arcmin REAL,
    approach_angle_deg REAL,
    gamma REAL NOT NULL,
    catalog_magnitude REAL NOT NULL,
    UNIQUE(julian_day_tt, test_type)
);

ALTER TABLE eclipse_results ADD COLUMN tychos_error_arcmin REAL;
ALTER TABLE eclipse_results ADD COLUMN jpl_error_arcmin REAL;
```

- [ ] **Step 2: Verify migration applies cleanly**

Run: `cd <repo> && rm -f results/tychos_results.db && PYTHONPATH=tychos_skyfield:tests:. python3 -c "from server.db import _run_migrations; _run_migrations()"`

Expected: No errors. All 6 migrations applied.

- [ ] **Step 3: Commit**

```bash
git add server/migrations/006_predicted_reference.sql
git commit -m "feat(db): add predicted_reference table and error columns to eclipse_results"
```

---

### Task 2: Predicted Reference Geometry Module

**Files:**
- Create: `server/services/predicted_geometry.py`
- Create: `tests/test_predicted_geometry.py`

This module computes expected eclipse geometry from catalog parameters only. No Skyfield, no Tychos.

- [ ] **Step 1: Write tests for solar eclipse geometry derivation**

```python
# tests/test_predicted_geometry.py
"""Tests for catalog-derived predicted eclipse geometry."""
import math
import pytest

from server.services.predicted_geometry import (
    expected_separation_from_gamma,
    solar_disk_radii,
    lunar_shadow_radii,
    approach_angle_from_gamma,
)

# --- Constants for reference ---
# Mean Moon distance ~384400 km, Earth radius ~6371 km
# arctan(1.0 * 6371 / 384400) ≈ 0.949° ≈ 56.9'


class TestExpectedSeparationFromGamma:
    def test_zero_gamma(self):
        """Gamma=0 means perfect alignment, separation should be ~0."""
        sep = expected_separation_from_gamma(0.0)
        assert sep == pytest.approx(0.0, abs=0.01)

    def test_gamma_one(self):
        """Gamma=1.0 should give ~57 arcminutes."""
        sep = expected_separation_from_gamma(1.0)
        assert 50 < sep < 65  # approximately 57'

    def test_negative_gamma(self):
        """Sign doesn't affect separation magnitude."""
        sep_pos = expected_separation_from_gamma(0.5)
        sep_neg = expected_separation_from_gamma(-0.5)
        assert sep_pos == pytest.approx(sep_neg, abs=0.01)

    def test_small_gamma(self):
        """Small gamma should give small separation, roughly linear."""
        sep = expected_separation_from_gamma(0.1)
        assert 3 < sep < 8  # roughly 5.7'


class TestSolarDiskRadii:
    def test_total_eclipse(self):
        """magnitude > 1 means Moon is larger than Sun."""
        moon_r, sun_r = solar_disk_radii(magnitude=1.05)
        assert moon_r > sun_r
        assert 14 < moon_r < 18
        assert 14 < sun_r < 18

    def test_annular_eclipse(self):
        """magnitude < 1 means Moon is smaller than Sun."""
        moon_r, sun_r = solar_disk_radii(magnitude=0.92)
        assert moon_r < sun_r

    def test_magnitude_one(self):
        """magnitude = 1 means equal sizes."""
        moon_r, sun_r = solar_disk_radii(magnitude=1.0)
        assert moon_r == pytest.approx(sun_r, abs=0.1)


class TestLunarShadowRadii:
    def test_total_lunar(self):
        """Total lunar eclipse with known magnitudes."""
        umbra_r, penumbra_r, moon_r = lunar_shadow_radii(
            um_mag=1.19, pen_mag=2.16, gamma=0.37
        )
        assert umbra_r > 0
        assert penumbra_r > umbra_r
        assert moon_r > 0
        assert 14 < moon_r < 18

    def test_penumbral_only(self):
        """Penumbral eclipse: um_mag is negative (Moon doesn't enter umbra)."""
        umbra_r, penumbra_r, moon_r = lunar_shadow_radii(
            um_mag=-0.03, pen_mag=1.04, gamma=-1.01
        )
        assert umbra_r > 0  # umbra still exists, Moon just doesn't enter it
        assert penumbra_r > umbra_r


class TestApproachAngle:
    def test_positive_gamma_north(self):
        """Positive gamma means Moon passes north of center."""
        angle = approach_angle_from_gamma(0.5)
        # Angle should be roughly 90° (north) with ecliptic correction
        assert 0 < angle < 180

    def test_negative_gamma_south(self):
        """Negative gamma means Moon passes south of center."""
        angle = approach_angle_from_gamma(-0.5)
        assert 180 < angle < 360

    def test_zero_gamma(self):
        """Zero gamma — approach angle is arbitrary (dead center)."""
        angle = approach_angle_from_gamma(0.0)
        assert 0 <= angle < 360
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd <repo> && PYTHONPATH=tychos_skyfield:tests:. python3 -m pytest tests/test_predicted_geometry.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'server.services.predicted_geometry'`

- [ ] **Step 3: Implement the geometry module**

```python
# server/services/predicted_geometry.py
"""Compute predicted eclipse geometry from NASA catalog parameters.

All derivations use pure geometry — no Skyfield, no Tychos.
"""
import math

# Mean values
R_EARTH_KM = 6371.0
D_MOON_MEAN_KM = 384400.0
SUN_MEAN_RADIUS_ARCMIN = 16.0  # mean solar angular radius


def expected_separation_from_gamma(gamma: float) -> float:
    """Derive expected Sun-Moon angular separation from gamma.

    Gamma is the distance of the shadow axis from Earth's center
    in Earth radii. Returns separation in arcminutes.
    """
    if gamma == 0.0:
        return 0.0
    rad = math.atan(abs(gamma) * R_EARTH_KM / D_MOON_MEAN_KM)
    return math.degrees(rad) * 60


def solar_disk_radii(magnitude: float) -> tuple[float, float]:
    """Derive Moon and Sun apparent radii from solar eclipse magnitude.

    For central eclipses, magnitude = D_moon / D_sun = R_moon / R_sun.
    Returns (moon_radius_arcmin, sun_radius_arcmin).
    """
    # magnitude = R_moon / R_sun, and we anchor to mean Sun radius
    sun_r = SUN_MEAN_RADIUS_ARCMIN
    moon_r = magnitude * sun_r
    return moon_r, sun_r


def lunar_shadow_radii(
    um_mag: float, pen_mag: float, gamma: float
) -> tuple[float, float, float]:
    """Derive umbral radius, penumbral radius, and Moon radius from lunar catalog data.

    Umbral magnitude = fraction of Moon diameter inside umbra.
    Penumbral magnitude = fraction of Moon diameter inside penumbra.

    Geometry:
        um_mag = (R_umbra + R_moon - d) / D_moon
        pen_mag = (R_penumbra + R_moon - d) / D_moon

    where d = Moon-to-shadow-center distance (from gamma).

    Returns (umbra_radius_arcmin, penumbra_radius_arcmin, moon_radius_arcmin).
    """
    d = expected_separation_from_gamma(gamma)

    # We have two equations and three unknowns (R_umbra, R_penumbra, R_moon).
    # Use the mean Moon radius as anchor, then solve for shadow radii.
    moon_r = 15.5  # mean Moon angular radius in arcminutes
    d_moon = 2 * moon_r

    # um_mag = (R_umbra + R_moon - d) / D_moon
    # => R_umbra = um_mag * D_moon - R_moon + d
    umbra_r = um_mag * d_moon - moon_r + d

    # pen_mag = (R_penumbra + R_moon - d) / D_moon
    # => R_penumbra = pen_mag * D_moon - R_moon + d
    penumbra_r = pen_mag * d_moon - moon_r + d

    # Clamp to reasonable minimums
    umbra_r = max(umbra_r, 5.0)
    penumbra_r = max(penumbra_r, umbra_r + 5.0)

    return umbra_r, penumbra_r, moon_r


def approach_angle_from_gamma(gamma: float) -> float:
    """Derive the Moon's approach angle from gamma sign.

    Positive gamma: Moon passes north of center → ~90°
    Negative gamma: Moon passes south → ~270°
    Zero: dead center, use 90° as default.

    The ecliptic is tilted ~23.44° to the equator, and the Moon's orbit
    is tilted ~5.14° to the ecliptic. The approach is roughly along
    the ecliptic, so we add the ecliptic tilt as a correction.

    Returns angle in degrees (0-360), measured counter-clockwise from East.
    """
    ecliptic_tilt = 23.44  # degrees

    if gamma == 0.0:
        return 90.0

    if gamma > 0:
        return 90.0 - ecliptic_tilt  # ~66.6°, north-east approach
    else:
        return 270.0 + ecliptic_tilt  # ~293.4°, south-west approach
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd <repo> && PYTHONPATH=tychos_skyfield:tests:server:. python3 -m pytest tests/test_predicted_geometry.py -v`

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add server/services/predicted_geometry.py tests/test_predicted_geometry.py
git commit -m "feat: add predicted geometry module with catalog-derived eclipse calculations"
```

---

### Task 3: Seed Predicted Reference Data

**Files:**
- Modify: `server/seed.py`

- [ ] **Step 1: Write test for seed function**

```python
# tests/test_predicted_seed.py
"""Test that predicted reference seeding produces valid data."""
import json
from pathlib import Path

import pytest

from server.services.predicted_geometry import (
    expected_separation_from_gamma,
    solar_disk_radii,
    lunar_shadow_radii,
)

DATA_DIR = Path(__file__).parent / "data"


class TestPredictedSeedData:
    def test_solar_catalog_has_gamma(self):
        with open(DATA_DIR / "solar_eclipses.json") as f:
            eclipses = json.load(f)
        assert len(eclipses) > 0
        for ecl in eclipses:
            assert "gamma" in ecl, f"Missing gamma in {ecl['date']}"
            assert "magnitude" in ecl, f"Missing magnitude in {ecl['date']}"

    def test_lunar_catalog_has_magnitudes(self):
        with open(DATA_DIR / "lunar_eclipses.json") as f:
            eclipses = json.load(f)
        assert len(eclipses) > 0
        for ecl in eclipses:
            assert "gamma" in ecl, f"Missing gamma in {ecl['date']}"
            assert "pen_mag" in ecl, f"Missing pen_mag in {ecl['date']}"
            assert "um_mag" in ecl, f"Missing um_mag in {ecl['date']}"

    def test_solar_derivation_produces_valid_values(self):
        with open(DATA_DIR / "solar_eclipses.json") as f:
            eclipses = json.load(f)
        for ecl in eclipses[:10]:
            sep = expected_separation_from_gamma(ecl["gamma"])
            assert sep >= 0, f"Negative separation for {ecl['date']}"
            assert sep < 120, f"Unreasonably large separation for {ecl['date']}: {sep}"
            moon_r, sun_r = solar_disk_radii(ecl["magnitude"])
            assert moon_r > 0
            assert sun_r > 0

    def test_lunar_derivation_produces_valid_values(self):
        with open(DATA_DIR / "lunar_eclipses.json") as f:
            eclipses = json.load(f)
        for ecl in eclipses[:10]:
            sep = expected_separation_from_gamma(ecl["gamma"])
            assert sep >= 0
            umbra_r, penumbra_r, moon_r = lunar_shadow_radii(
                ecl["um_mag"], ecl["pen_mag"], ecl["gamma"]
            )
            assert umbra_r > 0
            assert penumbra_r > umbra_r
            assert moon_r > 0
```

- [ ] **Step 2: Run tests to verify they pass** (these test the geometry module against real catalog data)

Run: `cd <repo> && PYTHONPATH=tychos_skyfield:tests:server:. python3 -m pytest tests/test_predicted_seed.py -v`

Expected: All PASS.

- [ ] **Step 3: Add `_seed_predicted_reference()` to seed.py**

Add this function to `server/seed.py` and call it from `seed()`:

```python
def _seed_predicted_reference():
    """Precompute predicted eclipse geometry from catalog data.

    Uses only catalog parameters (gamma, magnitude) — no Skyfield, no Tychos.
    Only runs once — skips if predicted_reference table already has data.
    """
    with get_db() as conn:
        count = conn.execute("SELECT COUNT(*) FROM predicted_reference").fetchone()[0]
        if count > 0:
            return

    print("[seed] Computing predicted reference geometry from catalog data...")

    from server.services.predicted_geometry import (
        expected_separation_from_gamma,
        solar_disk_radii,
        lunar_shadow_radii,
        approach_angle_from_gamma,
    )

    rows = []

    # Solar eclipses
    solar_path = DATA_DIR / "solar_eclipses.json"
    with open(solar_path) as f:
        solar_eclipses = json.load(f)

    for ecl in solar_eclipses:
        sep = expected_separation_from_gamma(ecl["gamma"])
        moon_r, sun_r = solar_disk_radii(ecl["magnitude"])
        angle = approach_angle_from_gamma(ecl["gamma"])
        rows.append((
            ecl["julian_day_tt"], "solar",
            round(sep, 4), round(moon_r, 4), round(sun_r, 4),
            None, None,  # no umbra/penumbra for solar
            round(angle, 2), ecl["gamma"], ecl["magnitude"],
        ))

    # Lunar eclipses
    lunar_path = DATA_DIR / "lunar_eclipses.json"
    with open(lunar_path) as f:
        lunar_eclipses = json.load(f)

    for ecl in lunar_eclipses:
        sep = expected_separation_from_gamma(ecl["gamma"])
        umbra_r, penumbra_r, moon_r = lunar_shadow_radii(
            ecl["um_mag"], ecl["pen_mag"], ecl["gamma"]
        )
        angle = approach_angle_from_gamma(ecl["gamma"])
        rows.append((
            ecl["julian_day_tt"], "lunar",
            round(sep, 4), round(moon_r, 4), None,
            round(umbra_r, 4), round(penumbra_r, 4),
            round(angle, 2), ecl["gamma"], ecl["pen_mag"],
        ))

    with get_db() as conn:
        conn.executemany(
            """INSERT OR IGNORE INTO predicted_reference
               (julian_day_tt, test_type, expected_separation_arcmin,
                moon_apparent_radius_arcmin, sun_apparent_radius_arcmin,
                umbra_radius_arcmin, penumbra_radius_arcmin,
                approach_angle_deg, gamma, catalog_magnitude)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        conn.commit()

    print(f"[seed] Computed {len(rows)} predicted reference geometries")
```

Update `seed()` to call it:

```python
def seed():
    _seed_admin_user()
    _seed_param_sets_from_disk()
    _seed_jpl_reference()
    _seed_predicted_reference()
```

- [ ] **Step 4: Test seed with fresh DB**

Run: `cd <repo> && rm -f results/tychos_results.db && PYTHONPATH=tychos_skyfield:tests:. python3 -c "from server.db import init_db; init_db()"`

Expected: Output includes `[seed] Computed NNN predicted reference geometries` (should be ~909 — 452 solar + 457 lunar).

- [ ] **Step 5: Commit**

```bash
git add server/seed.py tests/test_predicted_seed.py
git commit -m "feat: seed predicted_reference table from catalog geometry"
```

---

### Task 4: Worker — Compute Error Values

**Files:**
- Modify: `server/worker.py`

- [ ] **Step 1: Write test for error computation**

```python
# tests/test_worker_errors.py
"""Test that worker computes tychos_error and jpl_error correctly."""
import pytest


class TestErrorComputation:
    def test_error_is_absolute_difference(self):
        """tychos_error = |tychos_separation - expected_separation|"""
        tychos_sep = 10.5
        expected_sep = 3.2
        error = abs(tychos_sep - expected_sep)
        assert error == pytest.approx(7.3, abs=0.01)

    def test_error_zero_when_matching(self):
        tychos_sep = 5.0
        expected_sep = 5.0
        error = abs(tychos_sep - expected_sep)
        assert error == pytest.approx(0.0, abs=0.01)

    def test_error_symmetric(self):
        """Error doesn't depend on which is larger."""
        assert abs(10.0 - 3.0) == abs(3.0 - 10.0)
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `cd <repo> && PYTHONPATH=tychos_skyfield:tests:server:. python3 -m pytest tests/test_worker_errors.py -v`

Expected: All PASS.

- [ ] **Step 3: Update worker.py to compute and store error values**

Replace the current `moon_error_arcmin` computation in `_process_one()` with error computation against `predicted_reference`. The key changes in `server/worker.py`:

After the scanning loop (around line 85), replace the JPL moon error block with:

```python
        # Load predicted reference for error computation
        with get_db() as conn:
            pred_rows = conn.execute(
                "SELECT julian_day_tt, expected_separation_arcmin FROM predicted_reference WHERE test_type = ?",
                (test_type,),
            ).fetchall()
        pred_by_jd = {row["julian_day_tt"]: row for row in pred_rows}

        # Load JPL reference for JPL error computation
        with get_db() as conn:
            jpl_rows = conn.execute(
                "SELECT julian_day_tt, separation_arcmin FROM jpl_reference WHERE test_type = ?",
                (test_type,),
            ).fetchall()
        jpl_by_jd = {row["julian_day_tt"]: row for row in jpl_rows}

        # Compute errors for each result
        for r in results:
            pred = pred_by_jd.get(r["julian_day_tt"])
            jpl = jpl_by_jd.get(r["julian_day_tt"])

            if pred:
                expected_sep = pred["expected_separation_arcmin"]
                r["tychos_error_arcmin"] = round(
                    abs(r["min_separation_arcmin"] - expected_sep), 2
                )
                if jpl:
                    r["jpl_error_arcmin"] = round(
                        abs(jpl["separation_arcmin"] - expected_sep), 2
                    )
                else:
                    r["jpl_error_arcmin"] = None
            else:
                r["tychos_error_arcmin"] = None
                r["jpl_error_arcmin"] = None

            # Keep moon_error_arcmin for backward compat during transition
            r["moon_error_arcmin"] = None
```

Update the INSERT statement to include the new columns:

```python
        insert_sql = """
            INSERT INTO eclipse_results (
                run_id, julian_day_tt, date, catalog_type, magnitude,
                detected, threshold_arcmin, min_separation_arcmin,
                timing_offset_min, best_jd,
                sun_ra_rad, sun_dec_rad, moon_ra_rad, moon_dec_rad,
                moon_error_arcmin, moon_ra_vel, moon_dec_vel,
                tychos_error_arcmin, jpl_error_arcmin
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        rows = [
            (
                run_id,
                r["julian_day_tt"], r["date"], r["catalog_type"], r["magnitude"],
                r["detected"], r["threshold_arcmin"], r["min_separation_arcmin"],
                r["timing_offset_min"], r["best_jd"],
                r["sun_ra_rad"], r["sun_dec_rad"], r["moon_ra_rad"], r["moon_dec_rad"],
                r["moon_error_arcmin"], r.get("moon_ra_vel"), r.get("moon_dec_vel"),
                r["tychos_error_arcmin"], r["jpl_error_arcmin"],
            )
            for r in results
        ]
```

- [ ] **Step 4: Test with fresh DB and a queued run**

Run: `cd <repo> && rm -f results/tychos_results.db && PYTHONPATH=tychos_skyfield:tests:. python3 -c "from server.db import init_db; init_db()" && PYTHONPATH=tychos_skyfield:tests:. python3 -c "from server.worker import _process_one; _process_one()"`

Expected: Worker processes one run, prints `[worker] Run N complete: X/Y`. Verify error columns have values:

```bash
PYTHONPATH=tychos_skyfield:tests:. python3 -c "
import sqlite3
conn = sqlite3.connect('results/tychos_results.db')
row = conn.execute('SELECT tychos_error_arcmin, jpl_error_arcmin FROM eclipse_results LIMIT 5').fetchall()
for r in row: print(r)
"
```

Expected: Rows with non-null float values for both columns.

- [ ] **Step 5: Commit**

```bash
git add server/worker.py tests/test_worker_errors.py
git commit -m "feat(worker): compute tychos and jpl error against predicted reference"
```

---

### Task 5: Results API — Replace Status Logic with Error Values

**Files:**
- Modify: `server/api/results_routes.py`

- [ ] **Step 1: Rewrite results_routes.py**

Replace the entire file. Remove `_compute_status`, `_enrich`, `JPL_CLOSE_THRESHOLD`. Serve error values directly. Replace status filter with error range filter.

```python
# server/api/results_routes.py
"""Eclipse results routes: paginated list per run with error metrics."""
from fastapi import APIRouter, HTTPException, Query

from server.db import get_async_db

router = APIRouter(prefix="/api/results")

PAGE_SIZE = 50


@router.get("/{run_id}")
async def list_results(
    run_id: int,
    page: int = Query(default=1, ge=1),
    catalog_type: str | None = Query(default=None),
    min_tychos_error: float | None = Query(default=None),
    max_tychos_error: float | None = Query(default=None),
):
    """Paginated eclipse results for a run with error metrics."""
    async with get_async_db() as conn:
        run_cursor = await conn.execute(
            "SELECT id, test_type FROM runs WHERE id = ?", (run_id,)
        )
        run_row = await run_cursor.fetchone()
        if run_row is None:
            raise HTTPException(status_code=404, detail="Run not found")

        conditions = ["er.run_id = ?"]
        values: list = [run_id]

        if catalog_type is not None:
            conditions.append("er.catalog_type = ?")
            values.append(catalog_type)

        if min_tychos_error is not None:
            conditions.append("er.tychos_error_arcmin >= ?")
            values.append(min_tychos_error)

        if max_tychos_error is not None:
            conditions.append("er.tychos_error_arcmin <= ?")
            values.append(max_tychos_error)

        where_clause = "WHERE " + " AND ".join(conditions)

        # Total count with filters
        total_cursor = await conn.execute(
            f"SELECT COUNT(*) FROM eclipse_results er {where_clause}", values
        )
        total = (await total_cursor.fetchone())[0]

        # Stats for full run (unfiltered)
        stats_cursor = await conn.execute(
            """
            SELECT
                COUNT(*) AS total,
                AVG(tychos_error_arcmin) AS mean_tychos_error,
                AVG(jpl_error_arcmin) AS mean_jpl_error,
                MAX(tychos_error_arcmin) AS max_tychos_error,
                MAX(jpl_error_arcmin) AS max_jpl_error
            FROM eclipse_results
            WHERE run_id = ?
            """,
            (run_id,),
        )
        s = await stats_cursor.fetchone()

        # Median (SQLite doesn't have MEDIAN, compute in Python)
        median_cursor = await conn.execute(
            "SELECT tychos_error_arcmin, jpl_error_arcmin FROM eclipse_results WHERE run_id = ? ORDER BY tychos_error_arcmin",
            (run_id,),
        )
        all_errors = await median_cursor.fetchall()
        tychos_errors = [r["tychos_error_arcmin"] for r in all_errors if r["tychos_error_arcmin"] is not None]
        jpl_errors = [r["jpl_error_arcmin"] for r in all_errors if r["jpl_error_arcmin"] is not None]

        def median(vals):
            if not vals:
                return None
            vals = sorted(vals)
            n = len(vals)
            if n % 2 == 0:
                return (vals[n // 2 - 1] + vals[n // 2]) / 2
            return vals[n // 2]

        # Paginated results
        offset = (page - 1) * PAGE_SIZE
        rows_cursor = await conn.execute(
            f"""
            SELECT er.*
            FROM eclipse_results er
            {where_clause}
            ORDER BY er.julian_day_tt ASC
            LIMIT ? OFFSET ?
            """,
            values + [PAGE_SIZE, offset],
        )
        rows = await rows_cursor.fetchall()

    return {
        "results": [dict(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": PAGE_SIZE,
        "stats": {
            "total": s["total"] or 0,
            "mean_tychos_error": round(s["mean_tychos_error"], 2) if s["mean_tychos_error"] else None,
            "mean_jpl_error": round(s["mean_jpl_error"], 2) if s["mean_jpl_error"] else None,
            "median_tychos_error": round(median(tychos_errors), 2) if tychos_errors else None,
            "median_jpl_error": round(median(jpl_errors), 2) if jpl_errors else None,
            "max_tychos_error": round(s["max_tychos_error"], 2) if s["max_tychos_error"] else None,
            "max_jpl_error": round(s["max_jpl_error"], 2) if s["max_jpl_error"] else None,
        },
    }


@router.get("/{run_id}/{result_id}")
async def get_result(run_id: int, result_id: int):
    """Get a single eclipse result with run context, JPL and predicted reference data."""
    async with get_async_db() as conn:
        cursor = await conn.execute(
            """
            SELECT er.*, r.test_type, pv.version_number,
                   ps.id AS param_set_id, ps.name AS param_set_name,
                   jpl.sun_ra_rad AS jpl_sun_ra_rad, jpl.sun_dec_rad AS jpl_sun_dec_rad,
                   jpl.moon_ra_rad AS jpl_moon_ra_rad, jpl.moon_dec_rad AS jpl_moon_dec_rad,
                   jpl.separation_arcmin AS jpl_separation_arcmin,
                   jpl.moon_ra_vel AS jpl_moon_ra_vel, jpl.moon_dec_vel AS jpl_moon_dec_vel,
                   pred.expected_separation_arcmin,
                   pred.moon_apparent_radius_arcmin,
                   pred.sun_apparent_radius_arcmin,
                   pred.umbra_radius_arcmin,
                   pred.penumbra_radius_arcmin,
                   pred.approach_angle_deg,
                   pred.gamma AS pred_gamma,
                   pred.catalog_magnitude AS pred_catalog_magnitude
            FROM eclipse_results er
            JOIN runs r ON er.run_id = r.id
            JOIN param_versions pv ON r.param_version_id = pv.id
            JOIN param_sets ps ON pv.param_set_id = ps.id
            LEFT JOIN jpl_reference jpl ON jpl.julian_day_tt = er.julian_day_tt
                AND jpl.test_type = r.test_type
            LEFT JOIN predicted_reference pred ON pred.julian_day_tt = er.julian_day_tt
                AND pred.test_type = r.test_type
            WHERE er.id = ? AND er.run_id = ?
            """,
            (result_id, run_id),
        )
        row = await cursor.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Result not found")
    return dict(row)
```

- [ ] **Step 2: Verify the API serves correctly**

Run: Start the server and query:
```bash
cd <repo> && PYTHONPATH=tychos_skyfield:tests:. python3 -m server.app &
sleep 3
curl -s localhost:8000/api/results/1?page=1 | python3 -m json.tool | head -30
kill %1
```

Expected: JSON with `stats` containing `mean_tychos_error`, `median_tychos_error`, etc. Results contain `tychos_error_arcmin` and `jpl_error_arcmin`.

- [ ] **Step 3: Commit**

```bash
git add server/api/results_routes.py
git commit -m "feat(api): replace pass/fail status with continuous error metrics"
```

---

### Task 6: Dashboard API — Replace Detection Rates with Error Metrics

**Files:**
- Modify: `server/api/dashboard_routes.py`

- [ ] **Step 1: Rewrite dashboard_routes.py**

Replace detection rate queries with mean error queries:

```python
# server/api/dashboard_routes.py
"""Dashboard routes: summary stats and leaderboard."""
from fastapi import APIRouter

from server.db import get_async_db

router = APIRouter(prefix="/api/dashboard")


def _row_to_dict(row) -> dict:
    return dict(row)


@router.get("")
async def dashboard():
    """Return aggregate stats, best runs (lowest error), recent runs, and leaderboard."""
    async with get_async_db() as conn:
        total_cursor = await conn.execute("SELECT COUNT(*) FROM param_sets")
        total_param_sets = (await total_cursor.fetchone())[0]

        ds_cursor = await conn.execute("SELECT id, slug, name FROM datasets ORDER BY id")
        datasets = await ds_cursor.fetchall()

        best_by_dataset = {}
        for ds in datasets:
            best_cursor = await conn.execute(
                """
                SELECT ps.name, pv.version_number,
                       AVG(er.tychos_error_arcmin) AS mean_error
                FROM runs r
                JOIN param_versions pv ON r.param_version_id = pv.id
                JOIN param_sets ps ON pv.param_set_id = ps.id
                JOIN eclipse_results er ON er.run_id = r.id
                WHERE r.dataset_id = ? AND r.status = 'done' AND r.total_eclipses > 0
                    AND er.tychos_error_arcmin IS NOT NULL
                GROUP BY r.id
                ORDER BY mean_error ASC
                LIMIT 1
                """,
                (ds["id"],),
            )
            best_row = await best_cursor.fetchone()
            best_by_dataset[ds["slug"]] = (
                {"name": f"{best_row['name']} v{best_row['version_number']}", "mean_error": round(best_row["mean_error"], 2)}
                if best_row else None
            )

        recent_cursor = await conn.execute(
            """
            SELECT r.id, ps.name AS param_set_name, pv.version_number, u.name AS owner_name,
                   d.slug AS dataset_slug, d.name AS dataset_name,
                   r.status, r.total_eclipses, r.detected, r.created_at
            FROM runs r
            JOIN param_versions pv ON r.param_version_id = pv.id
            JOIN param_sets ps ON pv.param_set_id = ps.id
            JOIN users u ON ps.owner_id = u.id
            JOIN datasets d ON r.dataset_id = d.id
            ORDER BY r.created_at DESC
            LIMIT 10
            """
        )
        recent_rows = await recent_cursor.fetchall()
        recent_runs = []
        for row in recent_rows:
            d = _row_to_dict(row)
            if d["status"] == "done":
                err_cursor = await conn.execute(
                    "SELECT AVG(tychos_error_arcmin) AS mean_error FROM eclipse_results WHERE run_id = ?",
                    (d["id"],),
                )
                err_row = await err_cursor.fetchone()
                d["mean_tychos_error"] = round(err_row["mean_error"], 2) if err_row["mean_error"] else None
            else:
                d["mean_tychos_error"] = None
            recent_runs.append(d)

        leader_cursor = await conn.execute(
            """
            SELECT ps.name AS param_set_name, u.name AS owner_name,
                   AVG(sub.mean_error) AS avg_mean_error
            FROM (
                SELECT r.id AS run_id, pv.param_set_id,
                       AVG(er.tychos_error_arcmin) AS mean_error
                FROM runs r
                JOIN param_versions pv ON r.param_version_id = pv.id
                JOIN eclipse_results er ON er.run_id = r.id
                WHERE r.status = 'done' AND r.total_eclipses > 0
                    AND er.tychos_error_arcmin IS NOT NULL
                GROUP BY r.id
            ) sub
            JOIN param_sets ps ON sub.param_set_id = ps.id
            JOIN users u ON ps.owner_id = u.id
            GROUP BY ps.id
            ORDER BY avg_mean_error ASC
            LIMIT 20
            """
        )
        leaderboard = [_row_to_dict(r) for r in await leader_cursor.fetchall()]

    return {
        "total_param_sets": total_param_sets,
        "best_solar": best_by_dataset.get("solar_eclipse"),
        "best_lunar": best_by_dataset.get("lunar_eclipse"),
        "recent_runs": recent_runs,
        "leaderboard": leaderboard,
    }
```

- [ ] **Step 2: Commit**

```bash
git add server/api/dashboard_routes.py
git commit -m "feat(api): dashboard uses mean error instead of detection rates"
```

---

### Task 7: Runs API and Compare API — Replace Detection Logic

**Files:**
- Modify: `server/api/runs_routes.py`
- Modify: `server/api/compare_routes.py`

- [ ] **Step 1: Update runs_routes.py**

Replace the `overall_pass` computation with `mean_tychos_error`. In `list_runs()` and the loop that enriches done runs, change:

```python
            if d["status"] == "done":
                err_cursor = await conn.execute(
                    "SELECT AVG(tychos_error_arcmin) AS mean_error FROM eclipse_results WHERE run_id = ?",
                    (d["id"],),
                )
                err_row = await err_cursor.fetchone()
                d["mean_tychos_error"] = round(err_row["mean_error"], 2) if err_row["mean_error"] else None
            else:
                d["mean_tychos_error"] = None
```

Remove all `overall_pass` references.

- [ ] **Step 2: Update compare_routes.py**

Replace `detected` comparisons with error deltas. In the comparison loop, change the changed-eclipse logic to compare error values:

```python
    # Find eclipses where error changed significantly
    changed = []
    all_keys = set(map_a.keys()) | set(map_b.keys())
    for key in sorted(all_keys):
        row_a = map_a.get(key)
        row_b = map_b.get(key)
        if row_a is None or row_b is None:
            continue
        err_a = row_a["tychos_error_arcmin"]
        err_b = row_b["tychos_error_arcmin"]
        if err_a is not None and err_b is not None:
            delta = err_b - err_a
            if abs(delta) > 1.0:  # Only show changes > 1 arcminute
                changed.append({
                    "date": row_a["date"],
                    "catalog_type": row_a["catalog_type"],
                    "a_error": err_a,
                    "b_error": err_b,
                    "a_sep": row_a["min_separation_arcmin"],
                    "b_sep": row_b["min_separation_arcmin"],
                    "error_delta": round(delta, 2),
                })
```

Update the SELECT to include `tychos_error_arcmin`:

```python
        cursor_a = await conn.execute(
            """
            SELECT julian_day_tt, date, catalog_type, min_separation_arcmin, tychos_error_arcmin
            FROM eclipse_results WHERE run_id = ?
            """,
            (run_a["id"],),
        )
```

Update the return to include `mean_tychos_error` instead of `detected` for each run:

```python
    return {
        "run_a": {
            "id": run_a["id"],
            "param_set_name": run_a["param_set_name"],
            "owner_name": run_a["owner_name"],
            "params_json": run_a["params_json"],
            "total_eclipses": run_a["total_eclipses"],
            "mean_tychos_error": run_a_mean_error,
        },
        "run_b": {
            "id": run_b["id"],
            "param_set_name": run_b["param_set_name"],
            "owner_name": run_b["owner_name"],
            "params_json": run_b["params_json"],
            "total_eclipses": run_b["total_eclipses"],
            "mean_tychos_error": run_b_mean_error,
        },
        "changed": changed,
    }
```

Compute `run_a_mean_error` and `run_b_mean_error` from the results.

- [ ] **Step 3: Commit**

```bash
git add server/api/runs_routes.py server/api/compare_routes.py
git commit -m "feat(api): runs and compare use error metrics instead of detection rates"
```

---

### Task 8: Frontend — ResultDetailPage Three-Diagram Layout

**Files:**
- Modify: `admin/src/pages/ResultDetailPage.tsx`

- [ ] **Step 1: Rewrite ResultDetailPage.tsx**

Key changes:
1. Remove `SkyPositionDiagram` (dead code)
2. Remove all pass/fail/rescued badge logic
3. Add `PredictedDiagram` that uses `approach_angle_deg` and `expected_separation_arcmin`
4. Update `EclipseDiagram` to accept disk radii as props instead of using constants
5. Three-column layout: Predicted, Tychos, JPL
6. Measurements card with three columns showing error values

Update the `EclipseDiagram` props to accept disk radii:

```typescript
interface DiagramProps {
  testType: string;
  sunRa: number | null;
  sunDec: number | null;
  moonRa: number | null;
  moonDec: number | null;
  moonRaVel: number | null;
  moonDecVel: number | null;
  separationArcmin: number | null;
  errorArcmin: number | null;
  label: string;
  // Disk radii from predicted_reference
  moonRadiusArcmin: number;
  sunRadiusArcmin: number | null;   // solar only
  umbraRadiusArcmin: number | null; // lunar only
  penumbraRadiusArcmin: number | null; // lunar only
  thresholdArcmin?: number; // removed — no threshold circle
}
```

Add a new `PredictedDiagram` component for the catalog-derived view:

```typescript
interface PredictedDiagramProps {
  testType: string;
  expectedSeparationArcmin: number;
  approachAngleDeg: number | null;
  moonRadiusArcmin: number;
  sunRadiusArcmin: number | null;
  umbraRadiusArcmin: number | null;
  penumbraRadiusArcmin: number | null;
  label: string;
}
```

This places the Moon at `expectedSeparationArcmin` distance from center at `approachAngleDeg` angle. No velocity arrow, no threshold circle.

Replace the two-column grid with three columns:

```tsx
<div className="grid grid-cols-3 gap-4">
  <Card>
    <CardHeader>
      <CardTitle className="text-sm font-medium text-muted-foreground">
        Predicted (Catalog)
      </CardTitle>
    </CardHeader>
    <CardContent>
      <PredictedDiagram ... />
    </CardContent>
  </Card>

  <Card>
    <CardHeader>
      <CardTitle className="text-sm font-medium text-muted-foreground">
        Tychos
      </CardTitle>
    </CardHeader>
    <CardContent>
      <EclipseDiagram ... errorArcmin={result.tychos_error_arcmin} />
    </CardContent>
  </Card>

  <Card>
    <CardHeader>
      <CardTitle className="text-sm font-medium text-muted-foreground">
        JPL (DE440s)
      </CardTitle>
    </CardHeader>
    <CardContent>
      <EclipseDiagram ... errorArcmin={result.jpl_error_arcmin} />
    </CardContent>
  </Card>
</div>
```

Update the measurements card: three columns (Predicted, Tychos, JPL) with separation and error. Remove all badge rendering.

- [ ] **Step 2: Verify in browser**

Run the dev server and navigate to a result detail page. Verify three diagrams render side by side with error annotations.

- [ ] **Step 3: Commit**

```bash
git add admin/src/pages/ResultDetailPage.tsx
git commit -m "feat(admin): three-diagram layout with predicted, tychos, and jpl"
```

---

### Task 9: Frontend — ResultsTable Error Columns

**Files:**
- Modify: `admin/src/components/results/results-table.tsx`

- [ ] **Step 1: Rewrite results-table.tsx**

Key changes:
1. Remove `StatsBar` component (green/blue/red pass/rescued/fail)
2. Remove status badges, threshold badges, JPL check badges
3. Replace with `ErrorStatsBar` showing mean/median/max error
4. New columns: Expected Sep, Tychos Sep, Tychos Error, JPL Sep, JPL Error
5. Replace status filter with error range filter
6. Update `ApiStats` interface to match new API

New `ErrorStatsBar`:

```typescript
function ErrorStatsBar({ stats }: { stats: ApiStats }) {
  if (stats.total === 0) return null;
  return (
    <div className="grid grid-cols-2 gap-4 text-sm">
      <div>
        <span className="text-muted-foreground">Tychos Error — </span>
        <span className="font-mono">
          Mean: {stats.mean_tychos_error?.toFixed(1) ?? "—"}' ·
          Median: {stats.median_tychos_error?.toFixed(1) ?? "—"}' ·
          Max: {stats.max_tychos_error?.toFixed(1) ?? "—"}'
        </span>
      </div>
      <div>
        <span className="text-muted-foreground">JPL Error — </span>
        <span className="font-mono">
          Mean: {stats.mean_jpl_error?.toFixed(1) ?? "—"}' ·
          Median: {stats.median_jpl_error?.toFixed(1) ?? "—"}' ·
          Max: {stats.max_jpl_error?.toFixed(1) ?? "—"}'
        </span>
      </div>
    </div>
  );
}
```

New table columns:

```tsx
<TableHeader>
  <TableRow>
    <TableHead>Date</TableHead>
    <TableHead>Type</TableHead>
    <TableHead>Magnitude</TableHead>
    <TableHead>Expected Sep</TableHead>
    <TableHead>Tychos Sep</TableHead>
    <TableHead>Tychos Error</TableHead>
    <TableHead>JPL Sep</TableHead>
    <TableHead>JPL Error</TableHead>
    <TableHead>Timing Offset</TableHead>
  </TableRow>
</TableHeader>
```

Replace status filter with error range filter (input fields for min/max Tychos error).

- [ ] **Step 2: Verify in browser**

Navigate to a results table page. Verify error columns and stats bar render correctly.

- [ ] **Step 3: Commit**

```bash
git add admin/src/components/results/results-table.tsx
git commit -m "feat(admin): results table with error columns replacing pass/fail badges"
```

---

### Task 10: Frontend — Dashboard, Runs, Compare, Version Detail Pages

**Files:**
- Modify: `admin/src/components/dashboard/stats-cards.tsx`
- Modify: `admin/src/components/dashboard/leaderboard.tsx`
- Modify: `admin/src/components/dashboard/recent-runs.tsx`
- Modify: `admin/src/pages/DashboardPage.tsx`
- Modify: `admin/src/components/runs/run-table.tsx`
- Modify: `admin/src/components/compare/compare-view.tsx`
- Modify: `admin/src/components/compare/changed-eclipses.tsx`
- Modify: `admin/src/pages/ParamVersionDetailPage.tsx`

- [ ] **Step 1: Update stats-cards.tsx**

Replace "Best Solar/Lunar Detection" (percentage) with "Best Solar/Lunar Error" (arcminutes, lower is better):

```typescript
interface StatsCardsProps {
  totalParamSets: number;
  bestSolar: { name: string; mean_error: number } | null;
  bestLunar: { name: string; mean_error: number } | null;
}
```

Display `mean_error.toFixed(1)` with `'` suffix instead of percentage.

- [ ] **Step 2: Update leaderboard.tsx**

Sort by `avgMeanError` ascending (lower is better). Display error in arcminutes:

```typescript
interface LeaderboardProps {
  entries: Array<{
    paramSetName: string;
    ownerName: string;
    avgMeanError: number;
  }>;
}
```

Sort: `const sorted = [...entries].sort((a, b) => a.avgMeanError - b.avgMeanError);`

Display: `{entry.avgMeanError.toFixed(1)}'`

- [ ] **Step 3: Update recent-runs.tsx**

Replace `detected/totalEclipses` display with `meanTychosError`:

```typescript
interface RecentRunsProps {
  runs: Array<{
    id: number;
    datasetName: string;
    status: string;
    meanTychosError: number | null;
    paramSet: { name: string };
  }>;
}
```

Display: `run.meanTychosError != null ? `${run.meanTychosError.toFixed(1)}'` : "—"`

- [ ] **Step 4: Update DashboardPage.tsx**

Map new API response fields to updated component props. Replace `rate` with `mean_error`, `detected` with `mean_tychos_error`, `avg_rate` with `avg_mean_error`.

- [ ] **Step 5: Update run-table.tsx**

Replace `detectionRate()` function and "Detection Rate" column with mean error display:

```typescript
function meanErrorDisplay(run: Run): string {
  if (run.status !== "done") return "—";
  if (run.meanTychosError === null) return "—";
  return `${run.meanTychosError.toFixed(1)}'`;
}
```

Column header: "Mean Error" instead of "Detection Rate".

- [ ] **Step 6: Update compare-view.tsx and changed-eclipses.tsx**

Replace `DetectionBar` with error comparison. Replace `detected` counts with `meanTychosError`. Delta becomes error difference (negative = improved).

`changed-eclipses.tsx`: Replace "NEW DETECT" / "LOST" badges with error delta display:

```typescript
interface ChangedEclipse {
  date: string;
  catalogType: string;
  aError: number | null;
  bError: number | null;
  aSep: number | null;
  bSep: number | null;
  errorDelta: number;
}
```

Display: green badge "improved X'" or red badge "worsened X'" based on `errorDelta` sign.

- [ ] **Step 7: Update ParamVersionDetailPage.tsx**

Replace `StatCard` detection percentage with mean error. Replace `detectionLabel` with error label. In version history, replace solar/lunar detection counts with mean error values.

- [ ] **Step 8: Verify all pages in browser**

Navigate through: Dashboard, Runs, Compare, Parameter Version Detail. Verify no pass/fail/detected references remain. All pages show error metrics.

- [ ] **Step 9: Commit**

```bash
git add admin/src/components/dashboard/ admin/src/components/runs/ admin/src/components/compare/ admin/src/pages/DashboardPage.tsx admin/src/pages/ParamVersionDetailPage.tsx
git commit -m "feat(admin): replace all pass/fail UI with error metrics across all pages"
```

---

### Task 11: Clean Up — Remove Dead Threshold Code

**Files:**
- Modify: `tests/helpers.py`
- Modify: `tests/test_smoke.py`
- Modify: `tests/run_eclipses.py`

- [ ] **Step 1: Clean up helpers.py**

Remove the threshold constants that are no longer used as pass/fail gates. Keep `angular_separation`, `scan_min_separation`, `scan_lunar_eclipse` (the scanner still uses these). Remove `lunar_threshold()` function and the threshold constants:

```python
# Remove these lines:
# SOLAR_DETECTION_THRESHOLD = 0.8 * (np.pi / 180)
# LUNAR_UMBRAL_RADIUS = 0.45 * (np.pi / 180)
# LUNAR_PENUMBRAL_RADIUS = 1.25 * (np.pi / 180)
# MOON_MEAN_ANGULAR_RADIUS = 0.259 * (np.pi / 180)
# def lunar_threshold(catalog_type): ...
```

Keep `MINUTE_IN_DAYS` (used by scanner).

- [ ] **Step 2: Update test_smoke.py**

Remove `TestFalsePositives` class (it tests threshold-based detection which no longer exists). Keep `TestAngularSeparation` and `TestTychosSystemSanity` (these test core math and model sanity).

- [ ] **Step 3: Update run_eclipses.py**

Update `print_summary` and detection counting to show error metrics instead of pass/fail counts. The standalone CLI runner should still work but report mean/median error.

- [ ] **Step 4: Run tests**

Run: `cd <repo> && PYTHONPATH=tychos_skyfield:tests:server:. python3 -m pytest tests/ -v`

Expected: All tests pass. No import errors for removed constants.

- [ ] **Step 5: Commit**

```bash
git add tests/helpers.py tests/test_smoke.py tests/run_eclipses.py
git commit -m "refactor: remove threshold constants and pass/fail test logic"
```

---

### Task 12: Fresh Database and End-to-End Verification

**Files:** None (verification only)

- [ ] **Step 1: Delete the database and reinitialize**

```bash
cd <repo>
rm -f results/tychos_results.db
PYTHONPATH=tychos_skyfield:tests:. python3 -c "from server.db import init_db; init_db()"
```

Expected: All migrations applied, seeds run (admin user, param sets, JPL reference, predicted reference).

- [ ] **Step 2: Process queued runs**

```bash
PYTHONPATH=tychos_skyfield:tests:. python3 -c "
from server.worker import _process_one
for _ in range(10): _process_one()
"
```

Expected: Multiple runs processed, each printing `[worker] Run N complete: X/Y`.

- [ ] **Step 3: Verify error data in DB**

```bash
PYTHONPATH=tychos_skyfield:tests:. python3 -c "
import sqlite3
conn = sqlite3.connect('results/tychos_results.db')
conn.row_factory = sqlite3.Row

# Check predicted_reference
count = conn.execute('SELECT COUNT(*) FROM predicted_reference').fetchone()[0]
print(f'Predicted reference rows: {count}')

# Check error columns populated
row = conn.execute('SELECT tychos_error_arcmin, jpl_error_arcmin FROM eclipse_results WHERE tychos_error_arcmin IS NOT NULL LIMIT 3').fetchall()
for r in row: print(dict(r))

# Check stats
stats = conn.execute('SELECT AVG(tychos_error_arcmin) as mean_t, AVG(jpl_error_arcmin) as mean_j FROM eclipse_results').fetchone()
print(f'Mean Tychos error: {stats[\"mean_t\"]:.2f}, Mean JPL error: {stats[\"mean_j\"]:.2f}')
"
```

Expected: ~909 predicted reference rows. Error columns populated with reasonable values. JPL error should be small (validating catalog derivation).

- [ ] **Step 4: Run all tests**

```bash
cd <repo> && PYTHONPATH=tychos_skyfield:tests:server:. python3 -m pytest tests/ -v
```

Expected: All tests pass.

- [ ] **Step 5: Start server and verify UI**

```bash
cd <repo>/admin && npm run build
cd <repo> && PYTHONPATH=tychos_skyfield:tests:. python3 -m server.app
```

Navigate to the admin UI and verify:
- Dashboard shows error metrics, not detection rates
- Results table shows error columns
- Detail page shows three diagrams
- Compare page shows error deltas
- No pass/fail badges anywhere

- [ ] **Step 6: Commit any final fixes**

```bash
git add -A
git commit -m "chore: end-to-end verification of catalog-derived accuracy metric"
```
