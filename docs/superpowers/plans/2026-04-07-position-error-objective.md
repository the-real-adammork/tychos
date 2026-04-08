# Position-Error Objective for Autoresearch

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the autoresearch objective `mean(|timing_offset_min|)` with a directional, truth-anchored metric `mean(moon_position_error_arcmin)` that compares the tychos-predicted moon position at the catalog moment against the JPL reference moon position at the same moment. Capture signed Δ-RA and Δ-Dec components in aux stats so systematic biases are visible.

**Why:** The current metric is blind to two failure modes that the optimizer can actively exploit:

1. **Wrong-side miss.** `min_separation_arcmin` is unsigned. A moon passing 30′ north of the sun and a moon passing 30′ south of the sun both score 30′, but if the truth is "30′ north" the second case is ~60′ wrong. Driving `min_separation` down can move the moon further from truth while looking like progress.
2. **Right-time, wrong-place.** A windowed search can find a tychos-internal closest-approach moment that happens to coincide with catalog time (`timing_offset = 0`) while the predicted sun and moon are both displaced from where the truth says they are. The current objective rewards this.

The fix anchors the metric to truth (JPL moon position at `catalog_jd`) and records the miss as a 2-D signed vector — so both the magnitude and the *direction* of the miss inform iteration.

**Architecture:** The `jpl_reference` table already stores `sun_ra_rad / sun_dec_rad / moon_ra_rad / moon_dec_rad` at each catalog `julian_day_tt`. The research scanner currently ignores it. The fix joins those columns onto each event before scanning, has the scanner evaluate the tychos system **once at `catalog_jd`** (no window sweep) and emit signed Δ-RA / Δ-Dec / great-circle position-error per row. The objective rolls up to `mean(moon_position_error_arcmin)`. Old fields (`min_separation_arcmin`, `timing_offset_min`, the windowed best_jd) stay in scanner output as diagnostic aux but no longer feed the objective.

**Tech Stack:** Python (server/services/scanner.py, server/research/*), SQLite (jpl_reference table), tychos_skyfield model.

**Spec:** _none — design is contained in this plan._

---

### Task 1: JPL Reference Loader for Research Scans

**Why first:** Every later task assumes each event row carries `jpl_moon_ra_rad` etc. We need a clean loader before the scanner can use them.

**Files:**
- Modify: `server/research/subset.py` (add `attach_jpl_reference`)
- Modify: `server/research/cli.py` (call it from `_run_scan`)

- [ ] **Step 1: Add `attach_jpl_reference(events, dataset_slug)` to `server/research/subset.py`**

  Looks up `jpl_reference` rows by `julian_day_tt` for each event in the input list. Returns a new list where each event dict has been merged with `jpl_sun_ra_rad`, `jpl_sun_dec_rad`, `jpl_moon_ra_rad`, `jpl_moon_dec_rad`, `jpl_separation_arcmin`, `jpl_best_jd`. Raises `ValueError` if any event lacks a matching row (do **not** silently drop — that would mask seed gaps).

  Use a single batched `SELECT ... WHERE julian_day_tt IN (?, ?, ...)` query, not per-row lookups. The 452-event solar catalog must be a single round-trip.

  Use `get_db()` from `server/db.py` (same context manager `load_eclipses_for_dataset` uses).

- [ ] **Step 2: Wire it into `_run_scan` in `server/research/cli.py`**

  Before dispatching to the scanner, call `attach_jpl_reference(eclipses, dataset_slug)`. This means every research scan path (iterate, validate, search) automatically carries truth data.

- [ ] **Step 3: Test the loader against the live DB**

  Run: `cd <repo> && PYTHONPATH=tychos_skyfield:tests:. python3 -c "from server.research.subset import attach_jpl_reference, load_eclipses_for_dataset; ev=load_eclipses_for_dataset('solar_eclipse'); out=attach_jpl_reference(ev, 'solar_eclipse'); print(len(out), list(out[0].keys()))"`

  Expected: `452 [...event keys including jpl_moon_ra_rad...]`. Confirm no event was dropped and keys merged cleanly.

- [ ] **Step 4: Commit**

  ```bash
  /usr/bin/git add server/research/subset.py server/research/cli.py
  /usr/bin/git commit -m "feat(research): join jpl_reference onto scan events"
  ```

---

### Task 2: Scanner Emits Position-Error Columns

**Why:** Once the scanner has truth, it can compute the new fields per row. This task adds the new columns *without* changing the objective — old optimization remains in force, but logs start carrying the new diagnostic.

**Files:**
- Modify: `server/services/scanner.py` (both `_scan_solar_eclipses_serial` and `_scan_lunar_eclipses_serial`, plus the parallel paths' per-event helpers `_scan_one_solar_eclipse` / `_scan_one_lunar_eclipse`)

**New per-row fields:**

| Field | Definition | Sign |
|---|---|---|
| `moon_dra_arcmin` | `(tychos_moon_ra − jpl_moon_ra) · cos(jpl_moon_dec)` × deg→arcmin, evaluated at `catalog_jd` | signed |
| `moon_ddec_arcmin` | `(tychos_moon_dec − jpl_moon_dec)` × deg→arcmin, evaluated at `catalog_jd` | signed |
| `moon_position_error_arcmin` | great-circle distance between tychos_moon and jpl_moon at `catalog_jd`, in arcmin | unsigned |
| `sun_dra_arcmin` | analogous, sun | signed |
| `sun_ddec_arcmin` | analogous, sun | signed |
| `sun_position_error_arcmin` | analogous, sun | unsigned |

- [ ] **Step 1: Add `_evaluate_at_jd` helper in scanner.py**

  ```python
  def _evaluate_at_jd(system: T.TychosSystem, jd: float) -> tuple[float, float, float, float]:
      """Return (sun_ra, sun_dec, moon_ra, moon_dec) in radians at the given JD."""
  ```

  Should be a single ephemeris evaluation, not a window sweep. Look at how `scan_min_separation` already extracts positions for one timestamp and lift the inner step into this helper.

- [ ] **Step 2: Add `_position_error_fields(system, jd, ecl)` helper**

  Calls `_evaluate_at_jd(system, jd)`, reads `jpl_moon_ra_rad / jpl_moon_dec_rad / jpl_sun_ra_rad / jpl_sun_dec_rad` from `ecl`, computes the six fields above, returns them as a dict ready to merge into the row.

  Use `helpers.angular_separation` for the great-circle distance (already imported in jpl_scanner). Use `cos(jpl_moon_dec)` for the RA scaling so `moon_dra_arcmin` is in true on-sky arcmin, not raw RA arcmin.

- [ ] **Step 3: Merge into all four scan paths**

  In `_scan_solar_eclipses_serial`, `_scan_one_solar_eclipse`, `_scan_lunar_eclipses_serial`, `_scan_one_lunar_eclipse`: after the existing row dict is built, merge in `_position_error_fields(system, jd, ecl)`. The existing windowed-scan fields stay untouched.

  **Important:** evaluate the new fields at `jd` (= `ecl["julian_day_tt"]`, the catalog moment), not at `best_jd`. The whole point of the new metric is "where is your moon when truth says the eclipse is happening."

- [ ] **Step 4: Update the parallel pool worker if it pickles a stale function**

  `_scan_one_solar_eclipse` runs in a process pool (`_get_or_create_pool`). Verify that the pool picks up the new function (it imports from the module on each spawn — should be automatic, but check `_get_or_create_pool` for cached state that needs invalidation). If there's a pool cache keyed on function identity, restart it.

- [ ] **Step 5: Sanity check on a single event**

  ```bash
  cd <repo> && PYTHONPATH=tychos_skyfield:tests:. python3 -c "
  from server.research.cli import _run_scan, _load_job_state
  paths, current, baseline, fm, sub = _load_job_state('solar-sim-02')
  from server.research.subset import attach_jpl_reference
  ev = attach_jpl_reference(sub['events'][:1], sub['dataset_slug'])
  rows = _run_scan(sub['dataset_slug'], current, ev, half_window_hours=sub.get('scan_window_hours', 2.0))
  import json; print(json.dumps(rows[0], indent=2, default=str))
  "
  ```

  Expected: row contains the six new fields with sensible numeric values. Compare `moon_position_error_arcmin` to the existing `min_separation_arcmin`: in the current sim-02 best, the position error is **expected to be similar in scale OR larger** than the separation, never zero. If they're identical to many decimals, the helper is computing the wrong thing.

- [ ] **Step 6: Commit**

  ```bash
  /usr/bin/git add server/services/scanner.py
  /usr/bin/git commit -m "feat(scanner): record signed moon/sun position error vs jpl truth"
  ```

---

### Task 3: Sanity Diagnostic on sim-02 Current Best

**Why:** Before flipping the objective, confirm the new metric actually behaves the way the hypothesis predicts. If `moon_position_error_arcmin` turns out to be tightly correlated with the old objective on real data, the fix is academic and we should reconsider. If it's much larger and reveals systematic bias, the fix is justified.

**Files:**
- New (throwaway): `scripts/diagnose_position_error.py` _or_ run inline.

- [ ] **Step 1: Run the new metric on sim-02's current best (full solar catalog)**

  ```bash
  cd <repo> && PYTHONPATH=tychos_skyfield:tests:. python3 -c "
  from server.research.cli import _run_scan, _load_job_state
  from server.research.subset import attach_jpl_reference, load_eclipses_for_dataset
  paths, current, baseline, fm, sub = _load_job_state('solar-sim-02')
  full = attach_jpl_reference(load_eclipses_for_dataset(sub['dataset_slug']), sub['dataset_slug'])
  rows = _run_scan(sub['dataset_slug'], current, full, half_window_hours=sub.get('scan_window_hours', 2.0))
  import statistics as s
  pe = [r['moon_position_error_arcmin'] for r in rows]
  dra = [r['moon_dra_arcmin'] for r in rows]
  ddec = [r['moon_ddec_arcmin'] for r in rows]
  ms = [r['min_separation_arcmin'] for r in rows]
  to = [abs(r['timing_offset_min']) for r in rows]
  print('mean position_error_arcmin:', s.mean(pe))
  print('mean min_separation_arcmin:', s.mean(ms), '(old aux)')
  print('mean |timing_offset_min|: ', s.mean(to), '(old objective)')
  print('mean moon_dra_arcmin (signed):', s.mean(dra))
  print('mean moon_ddec_arcmin (signed):', s.mean(ddec))
  print('rms moon_dra_arcmin: ', (sum(d*d for d in dra)/len(dra))**0.5)
  print('rms moon_ddec_arcmin:', (sum(d*d for d in ddec)/len(ddec))**0.5)
  "
  ```

- [ ] **Step 2: Interpret**

  Three things to check:
  1. Is `mean(position_error)` substantially larger than `mean(min_separation)`? It should be — the old metric is the cross-track miss in tychos's own frame; the new one is the truth-anchored distance which includes along-track and the directional component.
  2. Is `mean(moon_dra)` or `mean(moon_ddec)` significantly non-zero? A non-zero signed mean is a smoking-gun systematic bias — points to which knob (`start_pos`, `speed`, `orbit_center_*`) needs tuning.
  3. Are RA-rms and Dec-rms similar, or is one axis much worse than the other? Asymmetric residuals suggest a tilt or offset axis is wrong.

  **Stop and think before continuing.** If the new metric reveals a large systematic bias, it means sim-02's current best is wronger than we knew, and the next iteration session should target the bias direction directly.

- [ ] **Step 3: Save the diagnostic output to the plan**

  Append a `## Sanity diagnostic results` section to this file with the printed numbers, so the plan record carries the before-and-after.

---

### Task 4: Flip the Objective

**Why:** Once the diagnostic confirms the new metric is meaningful, switch the optimizer to use it.

**Files:**
- Modify: `server/research/objective.py`

- [ ] **Step 1: Update `compute_objective`**

  Replace `sum(abs(r["timing_offset_min"]) for r in results)` with `sum(r["moon_position_error_arcmin"] for r in results)`. Same `len(results)` divisor. Same `EmptyResults` raise. Same single-float return.

- [ ] **Step 2: Update `aux_stats`**

  Add to the returned dict:
  ```
  moon_dra_arcmin_mean   # signed bias indicator
  moon_ddec_arcmin_mean  # signed bias indicator
  moon_dra_arcmin_rms
  moon_ddec_arcmin_rms
  mean_timing_offset_min_abs   # legacy, kept for back-comparison
  mean_separation_arcmin       # already there, keep
  ```

  All rounded to 3 decimals. The signed means are the diagnostically useful ones — they tell the agent which direction to push.

- [ ] **Step 3: Update the docstrings**

  Both `compute_objective` and `aux_stats` need their docstrings updated to reflect the new metric, units (arcmin), and what the signed components mean. Make it explicit that the objective is **arcmin-of-arc**, not minutes-of-time, so future readers don't confuse them.

- [ ] **Step 4: Update `server/research/templates/program.md.tmpl`**

  Anywhere the template references `mean(|timing_offset_min|)` or describes the objective, update to `mean(moon_position_error_arcmin)` and units. Re-read the file end-to-end before committing — there are likely 2–3 references including a sign-convention paragraph that needs revision.

- [ ] **Step 5: Run the unit tests for objective.py**

  ```bash
  cd <repo> && PYTHONPATH=tychos_skyfield:tests:. python3 -m pytest server/research/ -x -q 2>&1 | tail -20
  ```

  Existing objective tests will fail because the metric changed. Update them to construct rows with the new fields and assert against arcmin values. **Don't delete tests — fix them.**

- [ ] **Step 6: Commit**

  ```bash
  /usr/bin/git add server/research/objective.py server/research/templates/program.md.tmpl tests/
  /usr/bin/git commit -m "feat(research): switch objective to moon position error vs jpl truth"
  ```

---

### Task 5: Re-baseline sim-02 Under the New Metric

**Why:** Old log entries (`objective: 9.66`, `validation_objective: 13.74`) are in minutes-of-time. New entries will be in arcmin-of-arc. The numbers are not comparable; mixing them in the same log is a footgun. Re-baseline so the next iteration session has a clean reference.

**Files:**
- `params/research/solar-sim-02/log.jsonl` (append-only — just new entries)

- [ ] **Step 1: Append a metric-change marker to log.jsonl**

  Manual one-line entry: `{"iter": <next>, "ts": "...", "kind": "metric_change", "from": "mean_abs_timing_offset_min", "to": "mean_moon_position_error_arcmin", "note": "objective units flipped from min-of-time to arcmin-of-arc; entries below are not comparable to entries above"}`

- [ ] **Step 2: Re-run the standard sim-02 measurements**

  Run, in order, recording each result:
  1. `iterate` against `subset_phase.json` (current active cohort)
  2. `iterate` against `subset_saros.json`
  3. `iterate` against `subset_regression.json`
  4. `validate` (full solar catalog)
  5. `iterate` against `subset_lunar_val.json` (lunar full catalog)
  6. `iterate` against `test.json` (locked test set, 50 events) — **the new "honest" number**

- [ ] **Step 3: Update program.md "Prior findings" section**

  In `params/research/solar-sim-02/program.md`, add a `## sim-02 session 1 result (legacy metric)` block recording the old-metric numbers, and a `## New objective baseline (session 2)` block with the new-metric numbers from Step 2. Future agents need both to interpret the log file.

  Also revise Part C ("Leverage analysis") — the per-degree leverage numbers ("1° ≈ 109 min") were derived for the old timing metric. Under the new metric, 1° of `moon.start_pos` translates to ~60 arcmin of `moon_dra_arcmin` directly. Update the leverage table accordingly.

- [ ] **Step 4: Commit**

  ```bash
  /usr/bin/git add params/research/solar-sim-02/log.jsonl params/research/solar-sim-02/program.md
  /usr/bin/git commit -m "chore(research): re-baseline solar-sim-02 under new objective"
  ```

---

### Task 6: Verify and Hand Off

- [ ] **Step 1: Run a tiny sanity search under the new metric**

  ```bash
  ./research search solar-sim-02 --params moon.start_pos --budget 8 --scale 0.0001
  ```

  Expected: starting/best objectives reported in arcmin-of-arc, in the ~10–60 range (not the ~10 min range from before). If the numbers look like the old metric, the objective wasn't actually flipped.

- [ ] **Step 2: Verify the signed bias diagnostic shows up**

  Run a single `iterate` and check that `aux_stats` returns non-null `moon_dra_arcmin_mean` / `moon_ddec_arcmin_mean`. Confirm the CLI prints them (or at least logs them in log.jsonl).

- [ ] **Step 3: Update CLAUDE.md / autoresearch how-to docs (if any)**

  Search for any documentation that says `mean(|timing_offset_min|)` and update to the new metric name + units. `/usr/bin/grep -r "timing_offset_min" docs/ params/ server/README.md`

- [ ] **Step 4: Final commit + summary**

  ```bash
  /usr/bin/git status
  /usr/bin/git add -A
  /usr/bin/git commit -m "docs(research): update objective references to position error metric"
  ```

  Then write a brief summary in this plan file under `## Implementation results` noting:
  - new test-set number under the new metric
  - whether the directional diagnostic revealed systematic bias (and which axis)
  - any deferred follow-ups

---

## Out of scope for this plan

- **Switching to full-catalog iteration** (the other thing discussed in the same session). That's a separate plan — possibly enabled by this one if the new metric is fast enough that the windowed scan can be retired entirely. Capture as a follow-up.
- **Lunar metric specific tuning.** The new fields are computed for both solar and lunar paths, but the autoresearch loop currently runs one dataset at a time. No multi-dataset objective yet.
- **Sun position error in the objective.** The sun is barely tunable in the current allowlist; including `sun_position_error_arcmin` in the objective would mostly add a constant offset. Keep it as aux only.
- **Re-running sim-01.** sim-01 is frozen as a historical reference under the old metric. Don't re-baseline it.

## Known risks

- **JPL reference coverage.** If `jpl_reference` doesn't have rows for every event in every dataset cohort, Task 1 Step 1 will raise. Verify coverage before starting (`SELECT COUNT(*) FROM jpl_reference WHERE julian_day_tt IN (SELECT julian_day_tt FROM eclipse_catalog WHERE dataset_id = ?)`). If gaps exist, seed them via `seed.py` first.
- **Process pool staleness.** The scanner's persistent pool may cache the old serialized function. After Task 2, force-restart any running pool by killing python processes or by adding a pool-version bump.
- **Old log entries become un-replayable.** Anything that tries to compare the new objective number to a pre-flip log entry will be wrong by ~30–50%. The metric_change marker in Task 5 Step 1 is the only safeguard — make sure it's there.
- **Removing the windowed scan is tempting but separate.** This plan keeps the windowed scan running for backward-compatible aux fields. A follow-up plan can retire it if the new metric proves sufficient.
