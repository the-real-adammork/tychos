# Eclipse Scanner Regression Goldens Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Freeze current Tychos + JPL eclipse scanner output for the `v1-original/v1` parameter set as JSON goldens, and add slow-marked pytest tests that re-run the pure compute functions and compare with exact equality. This establishes a regression safety net before refactoring the scanner for speed.

**Architecture:** Extract the JPL compute logic from `server/seed.py` into a new pure function `server/services/jpl_scanner.py::scan_jpl_eclipses()` (no DB, takes catalog + ephemeris path, returns list of dicts). Add a one-time export script that reads the existing `v1-original/v1` run from the DB and dumps four JSON goldens to `tests/data/goldens/`. Add `tests/test_scanner_golden.py` with `@pytest.mark.slow` tests that load the goldens and compare field-by-field with `==`.

**Tech Stack:** Python 3, pytest, SQLite, NumPy, Skyfield + DE440s ephemeris.

**Related spec:** `docs/superpowers/specs/2026-04-07-eclipse-scanner-goldens-design.md`

---

## Known Facts (verified against the repo before plan was written)

- `server/services/scanner.py:47` `scan_solar_eclipses(params, eclipses)` and `:80` `scan_lunar_eclipses(params, eclipses)` are already pure — no DB access. **No refactor needed on the Tychos side.**
- JPL compute lives in `server/seed.py:286` `_seed_jpl_reference()` and its helper `:364` `_scan_jpl_min_jd(earth, eph, ts, center_jd, is_lunar)`. Both are tangled with DB reads/writes and must be extracted.
- The local DB at `results/tychos_results.db` contains completed runs for `v1-original/v1`:
  - `run_id=1`, dataset `solar_eclipse`, status `done`
  - `run_id=2`, dataset `lunar_eclipse`, status `done`
- Tables: `runs`, `param_versions`, `param_sets`, `datasets`, `eclipse_results`, `jpl_reference`, `eclipse_catalog`.
- Scanner-output fields (for projection from `eclipse_results` — enrichment columns `tychos_error_arcmin`, `jpl_error_arcmin`, `jpl_timing_offset_min`, `moon_error_arcmin` must be **excluded**): `julian_day_tt`, `date`, `catalog_type`, `magnitude`, `detected`, `threshold_arcmin`, `min_separation_arcmin`, `timing_offset_min`, `best_jd`, `sun_ra_rad`, `sun_dec_rad`, `moon_ra_rad`, `moon_dec_rad`, `moon_ra_vel`, `moon_dec_vel`.
- `jpl_reference` columns (all included in JPL goldens except `id` and `dataset_id`): `julian_day_tt`, `sun_ra_rad`, `sun_dec_rad`, `moon_ra_rad`, `moon_dec_rad`, `separation_arcmin`, `moon_ra_vel`, `moon_dec_vel`, `best_jd`.
- Existing pytest config: none (`pytest.ini`, `pyproject.toml`, `setup.cfg` do not exist). `tests/conftest.py` only adjusts `sys.path`.
- `params/v1-original/v1.json` wraps the orbital parameters under a `params` key (see `tests/test_scanner.py:42-45`).
- `de440s.bsp` is present at the repo root.

---

## File Structure

**New files:**
- `server/services/jpl_scanner.py` — pure JPL compute function
- `scripts/export_eclipse_goldens.py` — one-time export script
- `tests/test_scanner_golden.py` — golden regression tests
- `tests/data/goldens/solar_tychos_v1.json` — written by the export script
- `tests/data/goldens/lunar_tychos_v1.json` — written by the export script
- `tests/data/goldens/solar_jpl_v1.json` — written by the export script
- `tests/data/goldens/lunar_jpl_v1.json` — written by the export script
- `pytest.ini` — register `slow` marker, default-exclude via `addopts`

**Modified files:**
- `server/seed.py` — `_seed_jpl_reference()` and `_scan_jpl_min_jd()` become thin wrappers calling into `jpl_scanner.py`

---

## Task 1: Create pytest.ini with slow marker

**Files:**
- Create: `pytest.ini`

- [ ] **Step 1: Create pytest.ini**

```ini
[pytest]
markers =
    slow: marks tests as slow (deselected by default; run with -m slow)
addopts = -m "not slow"
```

- [ ] **Step 2: Verify existing fast tests still run by default**

Run: `pytest tests/test_scanner.py -v`
Expected: all existing tests in `test_scanner.py` PASS (they are not marked slow).

- [ ] **Step 3: Verify `-m slow` selects nothing yet**

Run: `pytest -m slow -v`
Expected: `no tests ran` or `0 selected` (no slow tests exist yet; exit code 5 from pytest is acceptable).

- [ ] **Step 4: Commit**

```bash
git add pytest.ini
git commit -m "test: register slow pytest marker, default-exclude from runs"
```

---

## Task 2: Extract pure JPL scanner function

**Files:**
- Create: `server/services/jpl_scanner.py`
- Modify: `server/seed.py` (lines 286-420 area — replace inline compute with calls into the new module)

- [ ] **Step 1: Create `server/services/jpl_scanner.py` with the extracted pure function**

The function must be a 1:1 behavioral copy of the inline compute in `_seed_jpl_reference()` and `_scan_jpl_min_jd()`. Do not change any math. Do not touch the DB.

```python
"""Pure JPL/Skyfield eclipse scanner — no DB, no global state.

Extracted from server/seed.py so regression goldens can exercise the
compute path in isolation.
"""
import math
from typing import Iterable

import numpy as np
from skyfield.api import load as skyfield_load

from helpers import angular_separation  # tests/helpers.py is on sys.path


_MIN_IN_DAYS = 1.0 / 1440.0
_HOUR_IN_DAYS = 1.0 / 24.0


def scan_jpl_eclipses(
    eclipses: Iterable[dict],
    ephemeris_path: str,
    is_lunar: bool,
) -> list[dict]:
    """Compute JPL Sun/Moon positions and min-separation for a catalog.

    Pure function: reads the DE ephemeris from ephemeris_path, but does
    not touch any database or global mutable state. Returns one dict per
    input eclipse with keys matching the jpl_reference table columns
    (minus id/dataset_id).
    """
    eph = skyfield_load(ephemeris_path)
    ts = skyfield_load.timescale()
    earth = eph["earth"]

    rows: list[dict] = []
    for ecl in eclipses:
        jd = ecl["julian_day_tt"]
        t = ts.tt_jd(jd)
        t2 = ts.tt_jd(jd + _HOUR_IN_DAYS)

        sun_ra, sun_dec, _ = earth.at(t).observe(eph["sun"]).radec()
        moon_ra, moon_dec, _ = earth.at(t).observe(eph["moon"]).radec()
        moon_ra2, moon_dec2, _ = earth.at(t2).observe(eph["moon"]).radec()

        s_ra, s_dec = sun_ra.radians, sun_dec.radians
        m_ra, m_dec = moon_ra.radians, moon_dec.radians
        m_ra_vel = float(moon_ra2.radians - m_ra)
        m_dec_vel = float(moon_dec2.radians - m_dec)

        if is_lunar:
            anti_ra = (s_ra + math.pi) % (2 * math.pi)
            anti_dec = -s_dec
            sep = float(np.degrees(angular_separation(m_ra, m_dec, anti_ra, anti_dec)) * 60)
        else:
            sep = float(np.degrees(angular_separation(s_ra, s_dec, m_ra, m_dec)) * 60)

        best_jd = _scan_jpl_min_jd(earth, eph, ts, jd, is_lunar)

        rows.append({
            "julian_day_tt": jd,
            "sun_ra_rad": float(s_ra),
            "sun_dec_rad": float(s_dec),
            "moon_ra_rad": float(m_ra),
            "moon_dec_rad": float(m_dec),
            "separation_arcmin": round(sep, 2),
            "moon_ra_vel": m_ra_vel,
            "moon_dec_vel": m_dec_vel,
            "best_jd": best_jd,
        })

    return rows


def _scan_jpl_min_jd(earth, eph, ts, center_jd: float, is_lunar: bool) -> float:
    """Scan Skyfield for the JD of minimum separation.

    Two-pass (5-minute coarse, 1-minute fine) over +/-2h around center_jd,
    then a 3-point quadratic refinement. Verbatim copy of the logic
    previously in server/seed.py::_scan_jpl_min_jd.
    """
    def sep_at(jd: float) -> float:
        t = ts.tt_jd(jd)
        s_ra, s_dec, _ = earth.at(t).observe(eph["sun"]).radec()
        m_ra, m_dec, _ = earth.at(t).observe(eph["moon"]).radec()
        s_ra_r, s_dec_r = s_ra.radians, s_dec.radians
        m_ra_r, m_dec_r = m_ra.radians, m_dec.radians
        if is_lunar:
            anti_ra = (s_ra_r + math.pi) % (2 * math.pi)
            anti_dec = -s_dec_r
            return float(angular_separation(m_ra_r, m_dec_r, anti_ra, anti_dec))
        return float(angular_separation(s_ra_r, s_dec_r, m_ra_r, m_dec_r))

    # Coarse pass: 5-minute steps across +/-2h
    best_jd = center_jd
    best_sep = float("inf")
    jd = center_jd - 2.0 / 24.0
    end = center_jd + 2.0 / 24.0 + 1e-12
    while jd <= end:
        s = sep_at(jd)
        if s < best_sep:
            best_sep = s
            best_jd = jd
        jd += 5 * _MIN_IN_DAYS

    # Fine pass: 1-minute steps within +/-10min of coarse minimum
    jd = best_jd - 10 * _MIN_IN_DAYS
    end = best_jd + 10 * _MIN_IN_DAYS + 1e-12
    while jd <= end:
        s = sep_at(jd)
        if s < best_sep:
            best_sep = s
            best_jd = jd
        jd += _MIN_IN_DAYS

    # Quadratic refinement on the 3-point bracket
    s_a = sep_at(best_jd - _MIN_IN_DAYS)
    s_b = sep_at(best_jd)
    s_c = sep_at(best_jd + _MIN_IN_DAYS)
    denom = s_a - 2.0 * s_b + s_c
    if denom > 0:
        offset = 0.5 * (s_a - s_c) / denom
        if -1.0 <= offset <= 1.0:
            refined_jd = best_jd + offset * _MIN_IN_DAYS
            if sep_at(refined_jd) < s_b:
                return refined_jd
    return best_jd
```

**Note on imports:** `helpers.angular_separation` lives in `tests/helpers.py`. The existing `conftest.py` adds `tychos_skyfield/` to `sys.path`; `tests/` is already on `sys.path` when running pytest from the repo root. For runtime use by `server/seed.py` the existing code already imports `from helpers import angular_separation` (see `server/seed.py:309`) so it resolves the same way. If import fails when running the export script outside pytest, the script (Task 4) will add `tests/` to `sys.path` explicitly.

- [ ] **Step 2: Add a quick smoke test for the new module**

Create `tests/test_jpl_scanner.py`:

```python
"""Smoke test for server/services/jpl_scanner.scan_jpl_eclipses.

Verifies the extracted pure function runs on a single known eclipse and
returns the expected field set. Full regression coverage is in
test_scanner_golden.py.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "tychos_skyfield"))
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from server.services.jpl_scanner import scan_jpl_eclipses

_EPHEMERIS = str(Path(__file__).parent.parent / "de440s.bsp")

_EXPECTED_KEYS = {
    "julian_day_tt",
    "sun_ra_rad",
    "sun_dec_rad",
    "moon_ra_rad",
    "moon_dec_rad",
    "separation_arcmin",
    "moon_ra_vel",
    "moon_dec_vel",
    "best_jd",
}


def test_solar_single_eclipse():
    # 2017-08-21 total solar eclipse
    rows = scan_jpl_eclipses(
        [{"julian_day_tt": 2457987.268519}],
        _EPHEMERIS,
        is_lunar=False,
    )
    assert len(rows) == 1
    assert set(rows[0].keys()) == _EXPECTED_KEYS
    # Sun and Moon should be very close (solar eclipse)
    assert rows[0]["separation_arcmin"] < 10.0


def test_lunar_single_eclipse():
    # 2018-01-31 total lunar eclipse
    rows = scan_jpl_eclipses(
        [{"julian_day_tt": 2458150.063194}],
        _EPHEMERIS,
        is_lunar=True,
    )
    assert len(rows) == 1
    assert set(rows[0].keys()) == _EXPECTED_KEYS
    # Moon should be very near the antisolar point (lunar eclipse)
    assert rows[0]["separation_arcmin"] < 60.0


def test_empty_input():
    assert scan_jpl_eclipses([], _EPHEMERIS, is_lunar=False) == []
```

- [ ] **Step 3: Run the smoke test to verify extraction is correct**

Run: `pytest tests/test_jpl_scanner.py -v`
Expected: all three tests PASS.

- [ ] **Step 4: Rewire `server/seed.py` to call the extracted function**

In `server/seed.py`, replace the body of `_seed_jpl_reference()` (lines ~306-361) and delete `_scan_jpl_min_jd` (lines ~364-420). The new `_seed_jpl_reference` keeps the DB orchestration but delegates compute to `scan_jpl_eclipses`.

Concretely, replace the compute block:

```python
    print("[seed] Computing JPL reference positions (this takes a moment)...")

    from server.services.jpl_scanner import scan_jpl_eclipses

    rows = []
    with get_db() as conn:
        datasets = _get_all_datasets(conn)
        for ds in datasets:
            is_lunar = ds["slug"] == "lunar_eclipse"
            eclipses = conn.execute(
                "SELECT julian_day_tt FROM eclipse_catalog WHERE dataset_id = ? ORDER BY julian_day_tt",
                (ds["id"],),
            ).fetchall()

            jpl_rows = scan_jpl_eclipses(
                [{"julian_day_tt": e["julian_day_tt"]} for e in eclipses],
                "de440s.bsp",
                is_lunar=is_lunar,
            )

            for r in jpl_rows:
                rows.append((
                    ds["id"],
                    r["julian_day_tt"],
                    r["sun_ra_rad"],
                    r["sun_dec_rad"],
                    r["moon_ra_rad"],
                    r["moon_dec_rad"],
                    r["separation_arcmin"],
                    r["moon_ra_vel"],
                    r["moon_dec_vel"],
                    r["best_jd"],
                ))

    with get_db() as conn:
        conn.executemany(
            """INSERT OR IGNORE INTO jpl_reference
               (dataset_id, julian_day_tt, sun_ra_rad, sun_dec_rad, moon_ra_rad, moon_dec_rad, separation_arcmin, moon_ra_vel, moon_dec_vel, best_jd)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        conn.commit()

    print(f"[seed] Computed {len(rows)} JPL reference positions")
```

Delete the old `_scan_jpl_min_jd` function entirely.

Also update `_backfill_jpl_best_jd` (around line 423) if it imports `_scan_jpl_min_jd` — replace with an import from `server.services.jpl_scanner` and call the private helper via a new public wrapper, OR (simpler) add a public `compute_best_jd(ephemeris_path, center_jd, is_lunar)` helper in `jpl_scanner.py` that loads the ephemeris and calls `_scan_jpl_min_jd` once. Read `_backfill_jpl_best_jd` before deciding — if it's dead code or not used in current flow, leave it alone and delete later.

- [ ] **Step 5: Verify seed.py still imports cleanly**

Run: `python -c "from server import seed"`
Expected: no errors.

- [ ] **Step 6: Re-run smoke test and existing tests**

Run: `pytest tests/test_jpl_scanner.py tests/test_scanner.py -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add server/services/jpl_scanner.py tests/test_jpl_scanner.py server/seed.py
git commit -m "refactor(jpl): extract pure scan_jpl_eclipses from seed"
```

---

## Task 3: Write the golden export script

**Files:**
- Create: `scripts/export_eclipse_goldens.py`

- [ ] **Step 1: Create the export script**

```python
"""One-time export of eclipse scanner goldens for v1-original/v1.

Reads the completed v1-original/v1 runs for both solar and lunar datasets
from the local SQLite DB and writes four JSON goldens to
tests/data/goldens/. Safe to re-run; overwrites existing files.

Usage:
    python scripts/export_eclipse_goldens.py
"""
import json
import sys
from pathlib import Path

# Make server package importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from server.db import get_db

REPO_ROOT = Path(__file__).parent.parent
GOLDENS_DIR = REPO_ROOT / "tests" / "data" / "goldens"

# Column projection: only the fields scan_solar_eclipses / scan_lunar_eclipses
# return. Enrichment columns (tychos_error_arcmin, jpl_error_arcmin,
# jpl_timing_offset_min, moon_error_arcmin) are intentionally excluded.
TYCHOS_COLUMNS = [
    "julian_day_tt",
    "date",
    "catalog_type",
    "magnitude",
    "detected",
    "threshold_arcmin",
    "min_separation_arcmin",
    "timing_offset_min",
    "best_jd",
    "sun_ra_rad",
    "sun_dec_rad",
    "moon_ra_rad",
    "moon_dec_rad",
    "moon_ra_vel",
    "moon_dec_vel",
]

# jpl_reference projection: everything except id and dataset_id.
JPL_COLUMNS = [
    "julian_day_tt",
    "sun_ra_rad",
    "sun_dec_rad",
    "moon_ra_rad",
    "moon_dec_rad",
    "separation_arcmin",
    "moon_ra_vel",
    "moon_dec_vel",
    "best_jd",
]

DATASETS = [
    ("solar_eclipse", "solar"),
    ("lunar_eclipse", "lunar"),
]


def _resolve_run_id(conn, dataset_slug: str) -> int:
    row = conn.execute(
        """
        SELECT r.id, r.status
          FROM runs r
          JOIN param_versions pv ON r.param_version_id = pv.id
          JOIN param_sets ps ON pv.param_set_id = ps.id
          JOIN datasets d ON r.dataset_id = d.id
         WHERE ps.name = 'v1-original'
           AND pv.version_number = 1
           AND d.slug = ?
         ORDER BY r.id
         LIMIT 1
        """,
        (dataset_slug,),
    ).fetchone()
    if row is None:
        raise SystemExit(
            f"No run found for v1-original/v1 dataset={dataset_slug}. "
            f"Run the scanner for this dataset first."
        )
    if row["status"] != "done":
        raise SystemExit(
            f"Run {row['id']} (v1-original/v1 {dataset_slug}) has status "
            f"{row['status']!r}, expected 'done'."
        )
    return row["id"]


def _resolve_dataset_id(conn, dataset_slug: str) -> int:
    row = conn.execute(
        "SELECT id FROM datasets WHERE slug = ?",
        (dataset_slug,),
    ).fetchone()
    if row is None:
        raise SystemExit(f"Dataset {dataset_slug!r} not found")
    return row["id"]


def _export_tychos(conn, run_id: int) -> list[dict]:
    cols = ", ".join(TYCHOS_COLUMNS)
    rows = conn.execute(
        f"SELECT {cols} FROM eclipse_results WHERE run_id = ? ORDER BY julian_day_tt",
        (run_id,),
    ).fetchall()
    return [{c: r[c] for c in TYCHOS_COLUMNS} for r in rows]


def _export_jpl(conn, dataset_id: int) -> list[dict]:
    cols = ", ".join(JPL_COLUMNS)
    rows = conn.execute(
        f"SELECT {cols} FROM jpl_reference WHERE dataset_id = ? ORDER BY julian_day_tt",
        (dataset_id,),
    ).fetchall()
    return [{c: r[c] for c in JPL_COLUMNS} for r in rows]


def _write_json(path: Path, data: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        # sort_keys=True for stable diffs; floats are written with Python's
        # default repr which round-trips exactly through json.loads.
        json.dump(data, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")


def main() -> None:
    GOLDENS_DIR.mkdir(parents=True, exist_ok=True)

    with get_db() as conn:
        for slug, short in DATASETS:
            run_id = _resolve_run_id(conn, slug)
            dataset_id = _resolve_dataset_id(conn, slug)

            tychos_rows = _export_tychos(conn, run_id)
            jpl_rows = _export_jpl(conn, dataset_id)

            tychos_path = GOLDENS_DIR / f"{short}_tychos_v1.json"
            jpl_path = GOLDENS_DIR / f"{short}_jpl_v1.json"

            _write_json(tychos_path, tychos_rows)
            _write_json(jpl_path, jpl_rows)

            print(f"[export] {slug}: {len(tychos_rows)} tychos rows → {tychos_path.relative_to(REPO_ROOT)}")
            print(f"[export] {slug}: {len(jpl_rows)} jpl rows    → {jpl_path.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the export script (produces the goldens)**

Run: `python scripts/export_eclipse_goldens.py`
Expected output: four lines reporting row counts for solar + lunar, each writing to `tests/data/goldens/`. Solar catalog is ~250 eclipses, lunar is ~650 (confirm from actual output).

- [ ] **Step 3: Verify four files exist and are non-empty**

Run: `ls -lh tests/data/goldens/`
Expected: four files — `solar_tychos_v1.json`, `lunar_tychos_v1.json`, `solar_jpl_v1.json`, `lunar_jpl_v1.json`.

- [ ] **Step 4: Spot-check one file**

Run: `python -c "import json; d=json.load(open('tests/data/goldens/solar_tychos_v1.json')); print(len(d), 'rows'); print(list(d[0].keys()))"`
Expected: number of rows printed and the key list matches `TYCHOS_COLUMNS` (order may differ because of `sort_keys`).

- [ ] **Step 5: Commit script and goldens**

```bash
git add scripts/export_eclipse_goldens.py tests/data/goldens/
git commit -m "test(goldens): export v1-original/v1 eclipse scanner goldens from DB"
```

---

## Task 4: Write the golden regression tests

**Files:**
- Create: `tests/test_scanner_golden.py`

- [ ] **Step 1: Create the test file**

```python
"""Golden-file regression tests for the eclipse scanners.

These tests load the full solar and lunar catalogs, run the pure
scan_solar_eclipses / scan_lunar_eclipses / scan_jpl_eclipses functions
with the v1-original/v1 parameter set, and compare every returned field
against frozen JSON goldens with exact equality.

They are marked @pytest.mark.slow because a full run is O(minutes). Run
with: pytest -m slow -v
"""
import json
import sys
from pathlib import Path

import pytest

# Mirror the sys.path setup used by tests/test_scanner.py
sys.path.insert(0, str(Path(__file__).parent.parent / "tychos_skyfield"))
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from server.services.scanner import scan_solar_eclipses, scan_lunar_eclipses
from server.services.jpl_scanner import scan_jpl_eclipses

_REPO_ROOT = Path(__file__).parent.parent
_PARAMS_PATH = _REPO_ROOT / "params" / "v1-original" / "v1.json"
_EPHEMERIS = str(_REPO_ROOT / "de440s.bsp")
_SOLAR_CATALOG = Path(__file__).parent / "data" / "solar_eclipses.json"
_LUNAR_CATALOG = Path(__file__).parent / "data" / "lunar_eclipses.json"
_GOLDENS = Path(__file__).parent / "data" / "goldens"


@pytest.fixture(scope="module")
def params():
    with open(_PARAMS_PATH) as f:
        return json.load(f)["params"]


@pytest.fixture(scope="module")
def solar_catalog():
    with open(_SOLAR_CATALOG) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def lunar_catalog():
    with open(_LUNAR_CATALOG) as f:
        return json.load(f)


def _load_golden(name: str) -> list[dict]:
    with open(_GOLDENS / name) as f:
        return json.load(f)


def _assert_rows_equal(actual: list[dict], expected: list[dict], label: str) -> None:
    """Compare row lists with exact equality and produce a helpful diff."""
    assert len(actual) == len(expected), (
        f"{label}: row count mismatch — actual={len(actual)} expected={len(expected)}"
    )
    mismatches = []
    for i, (a, e) in enumerate(zip(actual, expected)):
        if set(a.keys()) != set(e.keys()):
            mismatches.append(
                f"  row {i} (jd={a.get('julian_day_tt')}): key mismatch "
                f"actual={sorted(a.keys())} expected={sorted(e.keys())}"
            )
            continue
        for k in sorted(e.keys()):
            if a[k] != e[k]:
                mismatches.append(
                    f"  row {i} (jd={a.get('julian_day_tt')}) field {k!r}: "
                    f"actual={a[k]!r} expected={e[k]!r}"
                )
        if len(mismatches) >= 20:
            mismatches.append("  ... (truncated at 20)")
            break
    if mismatches:
        raise AssertionError(
            f"{label}: {len(mismatches)} mismatched fields\n" + "\n".join(mismatches)
        )


@pytest.mark.slow
def test_solar_tychos_matches_golden(params, solar_catalog):
    expected = _load_golden("solar_tychos_v1.json")
    actual = scan_solar_eclipses(params, solar_catalog)
    _assert_rows_equal(actual, expected, "solar tychos")


@pytest.mark.slow
def test_lunar_tychos_matches_golden(params, lunar_catalog):
    expected = _load_golden("lunar_tychos_v1.json")
    actual = scan_lunar_eclipses(params, lunar_catalog)
    _assert_rows_equal(actual, expected, "lunar tychos")


@pytest.mark.slow
def test_solar_jpl_matches_golden(solar_catalog):
    expected = _load_golden("solar_jpl_v1.json")
    # scan_jpl_eclipses only needs julian_day_tt from each entry
    actual = scan_jpl_eclipses(solar_catalog, _EPHEMERIS, is_lunar=False)
    _assert_rows_equal(actual, expected, "solar jpl")


@pytest.mark.slow
def test_lunar_jpl_matches_golden(lunar_catalog):
    expected = _load_golden("lunar_jpl_v1.json")
    actual = scan_jpl_eclipses(lunar_catalog, _EPHEMERIS, is_lunar=True)
    _assert_rows_equal(actual, expected, "lunar jpl")
```

- [ ] **Step 2: Verify test file is discovered but excluded by default**

Run: `pytest tests/test_scanner_golden.py -v`
Expected: 4 tests deselected (excluded by `-m "not slow"` from `pytest.ini`); exit code 5 is acceptable.

- [ ] **Step 3: Run the golden tests explicitly**

Run: `pytest tests/test_scanner_golden.py -m slow -v`
Expected: all 4 tests PASS. This takes several minutes — both the Tychos tests and the JPL tests run the full catalog.

- [ ] **Step 4: Sanity check — deliberately break one golden and confirm the test fails**

Edit `tests/data/goldens/solar_tychos_v1.json` and change one float (e.g. `min_separation_arcmin` of the first row) by a small amount. Save.

Run: `pytest tests/test_scanner_golden.py::test_solar_tychos_matches_golden -m slow -v`
Expected: FAIL with a message showing the row index, the field name, and the actual vs expected values.

Then revert the golden:

```bash
git checkout tests/data/goldens/solar_tychos_v1.json
```

Re-run: `pytest tests/test_scanner_golden.py::test_solar_tychos_matches_golden -m slow -v`
Expected: PASS.

- [ ] **Step 5: Commit the test file**

```bash
git add tests/test_scanner_golden.py
git commit -m "test(scanner): add slow-marked golden regression tests"
```

---

## Task 5: Run the full default and slow test suites

- [ ] **Step 1: Full default run**

Run: `pytest -v`
Expected: all existing fast tests PASS. Golden tests are deselected (shown as "deselected" in summary). No failures.

- [ ] **Step 2: Full slow run**

Run: `pytest -m slow -v`
Expected: 4 golden tests PASS.

- [ ] **Step 3: Document the new workflow in the plan's completion note**

No file change. Just confirm mentally:
- Fast dev loop: `pytest` (unchanged behavior)
- Before refactor: `pytest -m slow` → must pass
- After any refactor step: `pytest -m slow` → must still pass with exact equality

---

## Self-Review Notes

- **Spec coverage:** Export script (spec §Architecture → "Export script") = Task 3. JPL extraction (spec §"Current State") = Task 2. Four goldens (spec §"File Changes Summary") = Task 3 step 2. Four golden tests (spec §"Golden tests") = Task 4. Pytest slow marker (spec §"Golden tests") = Task 1. Tychos scanner untouched (spec §"Current State") — no task needed, verified.
- **Enrichment exclusion:** Task 3's `TYCHOS_COLUMNS` list explicitly excludes enrichment fields per the spec addendum.
- **Purity:** All functions exercised by golden tests take dicts/lists and return lists of dicts. Test file loads everything from JSON + `de440s.bsp` (static file, spec-approved).
- **Float precision:** Using `json.dump` default float formatting. Python's `json` module round-trips floats exactly via `repr()` since Python 3.1, so `loads(dumps(x)) == x` holds for all finite floats. Exact equality comparison is safe.
- **Type consistency:** `scan_jpl_eclipses` signature matches in both Task 2 creation and Task 4 test usage: `(eclipses: Iterable[dict], ephemeris_path: str, is_lunar: bool) -> list[dict]`.
- **No placeholders:** Every step has runnable code or concrete commands. Task 2 Step 4 contains an inline note about `_backfill_jpl_best_jd` that requires reading the current code before deciding — flagged but not left ambiguous.
