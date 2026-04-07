# Eclipse Scanner Regression Goldens

**Date:** 2026-04-07
**Status:** Design approved, pending implementation plan
**Owner:** Adam

## Purpose

Before refactoring the eclipse scanner for speed (parallelization + per-step algorithmic improvements), establish a deterministic regression safety net that proves the refactor is mathematically a no-op.

The safety net freezes the current full-catalog output of both the Tychos scanner and the JPL reference computation as JSON golden files, and adds slow-marked pytest tests that re-run the pure compute functions and compare against the goldens with **exact float equality**.

## Non-Goals

- Changing scanner math or algorithms (that happens *after* this safety net is in place).
- Replacing the existing fast single-eclipse tests in `tests/test_scanner.py` (they stay as-is).
- Testing worker.py DB-side orchestration or enrichment metrics — only the pure compute functions.
- Any new tolerance-based numerical comparison; exact equality only.

## Design Principles

1. **Functions under test are pure.** Inputs are dicts/lists (loaded from JSON at test setup); outputs are dicts/lists. Zero DB access, zero network, zero hidden state. The only file I/O allowed is loading the test fixture JSON and the `de440s.bsp` ephemeris (a deterministic static asset).
2. **Exact equality.** Golden comparison uses `==` on every field of every row. Any drift is a real signal and must be investigated, not papered over.
3. **Slow tests are opt-in.** Default `pytest` remains fast. Golden tests run via `pytest -m slow` or by explicit path.
4. **One-time export, committed to repo.** Goldens are generated once from the current DB state (v1-original / v1 run), committed, and thereafter treated as frozen ground truth until the user explicitly regenerates them.

## Current State (Verified)

**Tychos scanner is already pure.** `server/services/scanner.py:47` (`scan_solar_eclipses`) and `:80` (`scan_lunar_eclipses`) take `(params: dict, eclipses: list[dict])` and return `list[dict]`. No DB access inside. `load_eclipse_catalog` exists in the same file but is a separate helper not called by the scan functions. ✅ No refactor needed on the Tychos side.

**JPL compute is tangled with DB I/O.** `server/seed.py:286` (`_seed_jpl_reference`) reads eclipse catalogs from the DB, computes Sun/Moon positions via Skyfield + DE440s, runs a coarse/fine/quadratic min-separation scan (`_scan_jpl_min_jd` at `seed.py:364`), then writes results back to the `jpl_reference` table. The compute logic must be extracted into a pure function as part of this work.

## Architecture

### New pure JPL compute function

Create `server/services/jpl_scanner.py` with:

```python
def scan_jpl_eclipses(
    eclipses: list[dict],
    ephemeris_path: str,
    is_lunar: bool,
) -> list[dict]:
    """Run JPL/Skyfield eclipse scan for the given catalog.

    Pure function: no DB, no global state. Loads the DE ephemeris from
    ephemeris_path (static file) and computes per-eclipse Sun/Moon positions,
    separation, and best_jd via the same two-pass + quadratic refinement
    used by _scan_jpl_min_jd today.

    Returns one dict per eclipse with the same fields currently written to
    the jpl_reference table (dataset_id omitted; that's a DB concern).
    """
```

The existing `_seed_jpl_reference()` becomes a thin wrapper: it reads the catalog from the DB, calls `scan_jpl_eclipses()` for each dataset, and writes the returned rows to `jpl_reference`. No behavioral change to seeding.

`_scan_jpl_min_jd` moves into `jpl_scanner.py` as a private helper of the new pure function.

### Export script

`scripts/export_eclipse_goldens.py` — one-time-use (but idempotent), run by the developer after approving the design and before starting the refactor.

Behavior:
1. Open the DB via the existing `get_db()` helper.
2. Resolve the `v1-original` / `v1` run and its datasets (solar + lunar). If no completed run exists, print a clear error with instructions to run it first.
3. Query `eclipse_results` for each dataset and dump to:
   - `tests/data/goldens/solar_tychos_v1.json`
   - `tests/data/goldens/lunar_tychos_v1.json`

   **Important:** `eclipse_results` contains additional enrichment columns (e.g. `tychos_error_arcmin`, `jpl_error_arcmin`) computed by `worker.py` from JPL references. The export script must project **only** the columns that `scan_solar_eclipses` / `scan_lunar_eclipses` return — matching the keys in the dicts they produce. Any enrichment columns are skipped because the golden tests do not run the worker's enrichment step.
4. Query `jpl_reference` for each dataset and dump to:
   - `tests/data/goldens/solar_jpl_v1.json`
   - `tests/data/goldens/lunar_jpl_v1.json`
5. Each file is a JSON list of dicts, sorted by `julian_day_tt`, with keys sorted (for stable diffs). Floats are written with full precision (`json.dumps(..., allow_nan=False)` plus a custom encoder if needed to preserve round-trip equality — implementation detail for the plan).
6. Script is safe to re-run: overwrites existing files.

Exactly which columns get exported from each table is determined during planning by reading the current schema and scanner outputs, and documented in the plan.

### Golden tests

`tests/test_scanner_golden.py`, all marked `@pytest.mark.slow`. The `slow` marker is registered in `pytest.ini` or `pyproject.toml` (whichever the project uses; added if neither exists yet) and excluded from the default `pytest` run via `addopts = -m "not slow"`.

Fixtures load:
- `params/v1-original/v1.json` (already done in existing tests)
- `tests/data/solar_eclipses.json` / `lunar_eclipses.json` (existing catalog files)
- The four golden files

Tests:

1. `test_solar_tychos_matches_golden`
   - Calls `scan_solar_eclipses(params, solar_catalog)`.
   - Asserts the returned list exactly equals `solar_tychos_v1.json` (row-by-row, field-by-field, `==`).
   - On failure: produces a diff showing the first N mismatched rows with field name, expected, actual.

2. `test_lunar_tychos_matches_golden` — same for lunar.

3. `test_solar_jpl_matches_golden`
   - Calls `scan_jpl_eclipses(solar_catalog, "de440s.bsp", is_lunar=False)`.
   - Compares to `solar_jpl_v1.json` with exact equality.

4. `test_lunar_jpl_matches_golden` — same for lunar.

A shared `_assert_rows_equal(actual, expected)` helper produces the diff-style failure output so all four tests report mismatches identically.

## Data Flow

```
[ export phase — run once, by hand ]
DB (v1-original/v1 run)
  → export_eclipse_goldens.py
    → tests/data/goldens/*.json  (committed to repo)

[ test phase — run before & after refactor ]
params/v1-original/v1.json ─┐
tests/data/*_eclipses.json ─┼→ scan_*_eclipses()  ─→ actual rows
de440s.bsp ─────────────────┘                              │
                                                           ▼
                               tests/data/goldens/*.json → == assertion
```

## File Changes Summary

**New files:**
- `server/services/jpl_scanner.py` — pure JPL compute function (extracted from `seed.py`)
- `scripts/export_eclipse_goldens.py` — one-time golden export
- `tests/test_scanner_golden.py` — golden regression tests
- `tests/data/goldens/solar_tychos_v1.json`
- `tests/data/goldens/lunar_tychos_v1.json`
- `tests/data/goldens/solar_jpl_v1.json`
- `tests/data/goldens/lunar_jpl_v1.json`

**Modified files:**
- `server/seed.py` — `_seed_jpl_reference()` becomes a thin wrapper around `scan_jpl_eclipses()`; `_scan_jpl_min_jd` moves out.
- `pytest.ini` or `pyproject.toml` — register `slow` marker and default-exclude via `addopts`.

**Untouched:**
- `tests/test_scanner.py` — existing fast tests unchanged.
- `server/services/scanner.py` — already pure, no changes needed.
- `server/worker.py` — not under test; golden tests do not exercise it.

## Workflow After This Lands

1. Developer runs `python scripts/export_eclipse_goldens.py` once → commits the four JSON files.
2. Developer runs `pytest -m slow` → all four tests pass (proves extraction + goldens are correct).
3. Developer proceeds with the scanner refactor (parallelization + algorithmic improvements — separate spec).
4. After each refactor step, developer re-runs `pytest -m slow`; any failure means the refactor changed numerical results and must be investigated before proceeding.

## Open Questions Resolved During Brainstorming

- **Goldens source:** DB dump from v1-original/v1 run, not recomputed.
- **Scope:** Tychos + JPL, both sides, two files each (solar/lunar).
- **Tolerance:** Exact equality.
- **Test placement:** New `test_scanner_golden.py` with `@pytest.mark.slow`, existing fast tests untouched.
- **Purity:** Functions under test take JSON-compatible inputs and return JSON-compatible outputs; no DB. JPL side requires extraction refactor to meet this bar.
