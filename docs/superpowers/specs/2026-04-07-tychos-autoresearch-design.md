# Tychos Autoresearch — Design

**Date:** 2026-04-07
**Status:** Approved (pending user spec review)

## Summary

Add a karpathy-style [autoresearch](https://github.com/karpathy/autoresearch) loop
to tychos so a Claude Code agent can iteratively tune orbital parameters overnight
to improve eclipse-timing accuracy. The feature is intentionally tiny: one new
Python module exposing three CLI commands, one `program.md` template, and a
sandboxed scratch directory under `params/research/`. No DB schema changes, no
worker changes, no admin UI changes, no new server routes.

## Motivation

Manually hand-tuning the 8 fields × N bodies in a tychos param version to lower
timing errors on solar/lunar eclipses is slow and unstructured. The autoresearch
pattern gives us a way to let an AI agent run dozens of small experiments per
hour against a fast subset of the catalog, with a single scalar objective and
deterministic guardrails that prevent it from cheating its way to a "win."

The pattern's key insight is that the loop driver is just an LLM agent
(Claude/Codex) reading a `program.md`, editing one file, running one command,
and reading one number from stdout. We do not build an optimizer; we build the
file, the command, and the number.

## Design

### Architecture

A research job is a directory + a CLI + a markdown file. The agent loop runs
entirely inside a `claude` session you launch by hand.

```
You:    create job dir, pick base param version, write/edit program.md
        open `claude` in the repo with program.md as the entry prompt
Agent:  reads program.md → loops:
          edit params/research/<job>/current.json
          run `python -m server.research iterate <job>`     ← prints one number
          if better: run `python -m server.research validate <job>`  ← full-catalog check
          decide keep/revert based on stdout
          repeat until wall-clock budget exhausted
You:    wake up, read params/research/<job>/log.jsonl, promote winner
        manually into a real param version via the existing admin UI
```

No part of the existing server, worker, or admin UI is modified. The CLI runs
in-process, synchronously, with no DB writes (the only persistence is
`log.jsonl` inside the job directory).

### Sandbox layout

```
params/research/<job>/
├── program.md      # agent instructions (rendered from template at init)
├── baseline.json   # frozen copy of base params — never edited
├── current.json    # the ONE file the agent edits
├── subset.json     # frozen ~25 stratified eclipse JDs for this job
└── log.jsonl       # append-only history (iterate + validate entries)
```

`params/research/` is added to `.gitignore`. These directories are scratch space,
not project artifacts. Promoting a winner to a real param version is a manual
copy through the existing admin UI's "new param version" flow, which keeps
research output out of `params/` history until it earns a place there.

### CLI

New module `server/research/` with:

- `server/research/__init__.py`
- `server/research/__main__.py` — argparse entry point dispatching to subcommands
- `server/research/cli.py` — command implementations
- `server/research/objective.py` — objective computation (`mean(|timing_offset_min|)`)
- `server/research/sandbox.py` — sandbox dir creation, allowlist diff, log writer
- `server/research/subset.py` — deterministic stratified subset selection
- `server/research/templates/program.md.tmpl` — `program.md` template

Invoked as `python -m server.research <command>`.

#### `tychos research init <job-name> --base <param-version> --dataset <solar|lunar>`

Creates `params/research/<job>/` and populates:

- `current.json` — copy of the base param version's `params` block
- `baseline.json` — frozen copy of the same
- `program.md` — rendered from `templates/program.md.tmpl`, with `{job_name}`,
  `{dataset}`, `{base_param_version}`, `{allowlist}`, `{commands}` substituted
- `subset.json` — deterministic stratified subset of eclipse JDs (see below)
- `log.jsonl` — empty file

Fails (non-zero exit) if the job directory already exists, the base param
version doesn't exist, or the dataset slug is unknown.

#### `tychos research iterate <job>`

1. Loads `current.json` and `baseline.json` from the job directory.
2. Validates that only allowlisted keys differ from baseline (see Guardrails).
3. Loads `subset.json` (frozen list of eclipse rows captured at `init` time).
4. Runs `scan_solar_eclipses` or `scan_lunar_eclipses` (from
   `server/services/scanner.py`) against the subset only.
5. Computes objective: `mean(|timing_offset_min|)` across all subset events.
6. Computes auxiliary stats (printed for context, not used for the objective):
   - `mean_separation_arcmin`
   - `n_detected` / `n_total`
7. Computes a content hash of `current.json`'s allowlisted fields (`params_hash`).
8. If `params_hash` matches the most recent log entry, skips the scan and
   reprints the cached objective.
9. Appends to `log.jsonl`:
   ```json
   {"iter": 42, "ts": "2026-04-07T03:14:15Z", "kind": "iterate",
    "params_hash": "ab12cd…", "objective": 4.213,
    "mean_separation_arcmin": 31.5, "n_detected": 23, "n_total": 25}
   ```
10. Prints exactly one machine-readable line to stdout:
    ```
    objective: 4.213
    ```
    followed by a human-readable context block:
    ```
    mean_separation_arcmin: 31.5
    detected: 23/25
    ```
11. Exits 0.

Wall-time target: ~10–30 seconds on a ~25-event subset.

#### `tychos research validate <job>`

Identical to `iterate` except:

- Scans the **full** eclipse catalog for the job's dataset (not the subset).
- Logs `"kind": "validate"` instead of `"kind": "iterate"`.
- Prints `validation_objective: <n>` instead of `objective: <n>`.

Used by the agent (per `program.md` instructions) after every accepted
improvement on the subset, to catch subset overfitting before a "win" gets
locked in.

### Subset selection

`server/research/subset.py` exposes `select_subset(dataset_slug, n=25, seed=42)`.
At `init` time it loads the full eclipse catalog for the dataset, then picks `n`
events using stratified sampling:

- **Stratify by date range** — divide the catalog's date span into `n` equal
  buckets, pick one event per bucket. This ensures temporal coverage so the
  agent can't overfit to a single era.
- **Within each bucket, prefer catalog-type diversity** — for solar: total /
  annular / partial; for lunar: total / partial / penumbral. Round-robin by
  type when possible.
- **Deterministic** — same `(dataset, n, seed)` always returns the same JD list.
  This is critical: subset.json is frozen at init, but the algorithm itself
  must be reproducible so we can rebuild it if the file is lost.

Output written to `subset.json`:
```json
{
  "dataset_slug": "solar_eclipse",
  "n": 25,
  "seed": 42,
  "selected_at": "2026-04-07T03:00:00Z",
  "events": [
    {"julian_day_tt": 2299160.5, "date": "1582-10-14", "type": "total", ...},
    ...
  ]
}
```

The `iterate` command loads `events` directly from this file rather than
re-querying the DB, so the subset is truly frozen for the lifetime of the job.

### Objective

```python
def compute_objective(results: list[dict]) -> float:
    return mean(abs(r["timing_offset_min"]) for r in results)
```

That's it. No constraints, no penalty terms, no separation gating. Per design
discussion: pure timing optimization for the first version. Auxiliary stats
(mean separation, detection count) are printed alongside the objective for
context but do not affect it.

### Guardrails

Enforced inside `iterate` and `validate` before any scan runs:

1. **Allowlist check.** Parse the YAML frontmatter from `program.md` to get the
   `allowlist` (a list of `body.field` patterns, supports `body.*` to mean
   "all 8 fields on this body"). Diff `current.json` against `baseline.json`.
   If any key outside the allowlist has changed, hard-fail with an error
   naming the offending key. The agent must revert before it can iterate again.
2. **Schema check.** Every allowlisted value in `current.json` must still be a
   number (no None, no strings, no added/removed keys, no added/removed bodies).
3. **Hash dedup.** Compute a content hash over the allowlisted fields of
   `current.json`. If it matches the most recent log entry's `params_hash`,
   skip the scan and reprint the cached objective. Cheap insurance against the
   agent burning iterations on no-op edits.

No other guardrails. In particular: separation/direction are not constrained.
The agent is free to make changes that lower timing at the cost of separation;
the validation pass against the full catalog (per the loop in `program.md`) is
the only safety net against subset overfitting.

### `program.md` template

`server/research/templates/program.md.tmpl`:

```markdown
---
job: {job_name}
dataset: {dataset}
base_param_version: {base_param_version}
allowlist:
  - moon.*
  - moon_def_a.*
  - moon_def_b.*
  - sun.*
  - sun_def.*
  - earth.*
---

# Research job: {job_name}

## Goal
Lower `mean(|timing_offset_min|)` on the {dataset} subset by editing
`params/research/{job_name}/current.json`. Lower is better.

## The loop
1. Form a hypothesis about which allowlisted parameter to change and why.
2. Edit `current.json` (only keys matching the allowlist above).
3. Run: `python -m server.research iterate {job_name}`
   - Read stdout for `objective: <number>`.
4. If the new objective is **lower** than the current best:
   - Run: `python -m server.research validate {job_name}`
   - If `validation_objective` is also lower than the previous best validation,
     keep the edit and update your "current best" mental note.
   - If validation got *worse*, revert the edit (subset overfit) and note it.
5. If the objective got worse, revert `current.json` and try a different change.
6. Repeat until I stop you or your wall-clock budget is exhausted.

## Constraints
- **Only edit `current.json`.** Never touch `baseline.json`, `subset.json`, or
  any other file.
- **Only edit allowlisted keys.** The CLI will hard-fail if you don't.
- **One change at a time** when possible — easier to attribute wins.

## Background
[TODO: fill in physics context — what timing_offset_min means, how moon.speed
relates to the lunar sidereal rate, how earth.speed affects geocentric apparent
motion, which deferent fields shape the lunar epicycle, etc. This section is
the main lever for making the agent productive; iterate on it over time.]
```

The `Background` section is intentionally a TODO at template-render time. It's
the part you tune over time to teach the agent the physics; locking it down in
the template would defeat the point.

### Allowlist for the first job

The first job's allowlist (encoded in `program.md` frontmatter, not in code):

- `moon.*`
- `moon_def_a.*`
- `moon_def_b.*`
- `sun.*`
- `sun_def.*`
- `earth.*`

48 numbers total. Future jobs may widen, narrow, or change this freely by
editing the frontmatter — the CLI re-parses it on every iterate call.

### Stopping criteria

The CLI does not enforce stopping. The agent stops when its wall-clock budget
(told to it in the `claude` session prompt, e.g. "run for 6 hours") is
exhausted. This matches the karpathy pattern exactly: the human controls the
budget at session-launch time, not the tooling.

### Validation cadence

The agent runs `validate` after every accepted improvement (i.e., every time
`iterate` returns a new best). This is encoded in `program.md` step 4, not in
the CLI. Validation is cheap insurance: accepted improvements are rare relative
to total iterations, so the full-catalog cost is amortized.

## Testing

`tests/research/` (new directory):

**Unit tests** (`tests/research/test_sandbox.py`, `test_objective.py`, `test_subset.py`):

- `test_allowlist_accepts_allowed_key_change`
- `test_allowlist_rejects_disallowed_key_change` — must hard-fail with the
  offending key name in the error
- `test_allowlist_rejects_added_key`
- `test_allowlist_rejects_removed_key`
- `test_allowlist_glob_expansion` — `moon.*` matches all 8 moon fields
- `test_objective_mean_abs_timing` — fixture results, hand-computed expected
- `test_objective_handles_empty_results` — should raise, not silently return 0
- `test_subset_is_deterministic` — same seed → same JDs
- `test_subset_stratifies_by_date` — bucket coverage assertion
- `test_subset_prefers_type_diversity` — within-bucket type spread
- `test_log_writer_appends_jsonl` — multiple writes produce N lines
- `test_hash_dedup_skips_scan` — second iterate with same params hits cache

**Smoke test** (`tests/research/test_smoke.py`):

- `test_init_then_iterate_end_to_end` — runs `init` against a tiny fixture
  catalog (3-5 eclipses, fixture DB), then `iterate`, asserts:
  - `current.json`, `baseline.json`, `program.md`, `subset.json`, `log.jsonl`
    exist
  - stdout contains `objective: <float>`
  - `log.jsonl` has exactly one entry with `kind: "iterate"`
- `test_init_then_validate_end_to_end` — same but for `validate`

The smoke test exercises the full CLI wiring (argparse → command dispatch →
sandbox → scanner → objective → log → stdout) against a real (small) DB and
real scanner code. No mocks of the scanner — the whole point is to catch
wiring breaks.

## Out of scope

Explicitly **not** in this work, listed here so they don't sneak in:

- **No directional separation field.** The new `separation_pa_deg` field on
  `eclipse_results` (capturing which side of the sun the moon falls on) was
  discussed and deferred. It is not part of the objective and is not added to
  the schema in this work. Tracked separately as future work.
- **No admin UI for jobs.** No "create research job" page, no live progress
  view, no "promote winner" button. Promotion is a manual copy through the
  existing param-version flow.
- **No DB-backed jobs.** The whole feature lives in `params/research/<job>/`
  on disk. No new tables, no new migrations.
- **No worker integration.** The worker doesn't know research jobs exist.
- **No optimizer.** No CMA-ES, no Bayesian opt, no coordinate descent. The
  agent is the optimizer.
- **No multi-dataset jobs.** A job targets one dataset (solar OR lunar). If
  you want to tune both, run two jobs.
- **No constraint on separation/direction in the objective.** Pure timing.

## Future work

- Directional separation field (`separation_pa_deg`) on `eclipse_results`,
  computed in `scanner.py`, surfaced in admin results table and detail page,
  with a new migration. Display only — not added to the autoresearch objective
  unless future experience shows the agent needs it as a guardrail.
- Optional admin UI to browse `params/research/<job>/log.jsonl` history and
  one-click promote a winner.
- Optional second job tier that combines solar + lunar in a single objective.
- Background section content for `program.md` — accumulated physics knowledge
  that makes future agent runs more productive.

## File-by-file change list

**New files:**
- `server/research/__init__.py`
- `server/research/__main__.py`
- `server/research/cli.py`
- `server/research/objective.py`
- `server/research/sandbox.py`
- `server/research/subset.py`
- `server/research/templates/program.md.tmpl`
- `tests/research/__init__.py`
- `tests/research/conftest.py` (small fixture catalog)
- `tests/research/test_sandbox.py`
- `tests/research/test_objective.py`
- `tests/research/test_subset.py`
- `tests/research/test_smoke.py`

**Modified files:**
- `.gitignore` — add `params/research/`

**No other files touched.** No DB migrations, no schema changes, no admin
changes, no worker changes, no existing-server-route changes.
