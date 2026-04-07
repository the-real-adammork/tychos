# Tychos Autoresearch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a karpathy-style autoresearch loop that lets a Claude Code agent iteratively tune orbital parameters to lower `mean(|timing_offset_min|)` on solar/lunar eclipses, with deterministic guardrails and a fast subset-based inner loop.

**Architecture:** A single new Python module `server/research/` exposing three subcommands (`init`, `iterate`, `validate`) via `python -m server.research`. Each command is synchronous, in-process, and operates on a sandboxed scratch directory under `params/research/<job>/`. The agent loop runs entirely inside a `claude` session driven by a per-job `program.md`. No DB schema changes, no worker integration, no admin UI.

**Tech Stack:** Python 3 (stdlib only — argparse, json, hashlib, pathlib), pytest, existing `server/services/scanner.py` and `server/db.py`.

**Spec:** `docs/superpowers/specs/2026-04-07-tychos-autoresearch-design.md`

---

## File Structure

**New files:**
- `server/research/__init__.py` — empty
- `server/research/__main__.py` — argparse entry point
- `server/research/cli.py` — `cmd_init`, `cmd_iterate`, `cmd_validate`
- `server/research/sandbox.py` — `load_sandbox`, `diff_against_baseline`, `params_hash`, `append_log`, `read_log_tail`
- `server/research/allowlist.py` — `parse_allowlist`, `expand_globs`, `check_diff_against_allowlist`
- `server/research/objective.py` — `compute_objective`
- `server/research/subset.py` — `select_subset`, `load_eclipses_for_dataset`
- `server/research/program_md.py` — `parse_frontmatter`, `render_template`
- `server/research/templates/program.md.tmpl`
- `tests/research/__init__.py`
- `tests/research/conftest.py` — fixtures: tiny eclipse list, baseline params dict, tmp job dir
- `tests/research/test_allowlist.py`
- `tests/research/test_sandbox.py`
- `tests/research/test_objective.py`
- `tests/research/test_subset.py`
- `tests/research/test_program_md.py`
- `tests/research/test_smoke.py`

**Modified files:**
- `.gitignore` — add `params/research/`

---

## Task 1: Scaffolding and `.gitignore`

**Files:**
- Create: `server/research/__init__.py`
- Create: `server/research/__main__.py`
- Create: `tests/research/__init__.py`
- Modify: `.gitignore`

- [ ] **Step 1: Create empty package files**

```bash
mkdir -p server/research/templates tests/research
```

Create `server/research/__init__.py` with content:
```python
"""Tychos autoresearch — agent-driven parameter tuning loop."""
```

Create `tests/research/__init__.py` empty.

- [ ] **Step 2: Create `server/research/__main__.py` with stub argparse**

```python
"""Entry point: `python -m server.research <command>`."""
import argparse
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m server.research")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Create a new research job directory")
    p_init.add_argument("job", help="Job name (directory name under params/research/)")
    p_init.add_argument("--base", required=True, help="Base param version, e.g. v1-original/v2")
    p_init.add_argument("--dataset", required=True, choices=["solar", "lunar"])
    p_init.add_argument("--subset-size", type=int, default=25)
    p_init.add_argument("--seed", type=int, default=42)

    p_iter = sub.add_parser("iterate", help="Run one subset experiment")
    p_iter.add_argument("job")

    p_val = sub.add_parser("validate", help="Run a full-catalog validation")
    p_val.add_argument("job")

    args = parser.parse_args(argv)

    from server.research import cli
    if args.command == "init":
        return cli.cmd_init(args)
    if args.command == "iterate":
        return cli.cmd_iterate(args)
    if args.command == "validate":
        return cli.cmd_validate(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Create empty `server/research/cli.py` with stubs**

```python
"""CLI command implementations for `python -m server.research`."""


def cmd_init(args) -> int:
    raise NotImplementedError


def cmd_iterate(args) -> int:
    raise NotImplementedError


def cmd_validate(args) -> int:
    raise NotImplementedError
```

- [ ] **Step 4: Add `params/research/` to `.gitignore`**

Read current `.gitignore`, then add a new line:
```
params/research/
```
under an existing section (or at end with a comment `# autoresearch scratch dirs`).

- [ ] **Step 5: Verify the entry point loads**

Run:
```bash
source tychos_skyfield/.venv/bin/activate && python -m server.research --help
```
Expected: argparse help output listing `init`, `iterate`, `validate`. No tracebacks.

- [ ] **Step 6: Commit**

```bash
git add server/research/ tests/research/ .gitignore
git commit -m "feat(research): scaffold autoresearch package + entry point"
```

---

## Task 2: Allowlist parsing and glob expansion

**Files:**
- Create: `server/research/allowlist.py`
- Create: `tests/research/test_allowlist.py`

- [ ] **Step 1: Write failing tests**

`tests/research/test_allowlist.py`:
```python
import pytest

from server.research.allowlist import (
    expand_globs,
    check_diff_against_allowlist,
    AllowlistViolation,
)

ALL_FIELDS = (
    "orbit_radius",
    "orbit_center_a",
    "orbit_center_b",
    "orbit_center_c",
    "orbit_tilt_a",
    "orbit_tilt_b",
    "start_pos",
    "speed",
)


def _params(moon_speed=83.0, sun_speed=6.28, mars_speed=-3.34):
    return {
        "moon": {f: 0.0 for f in ALL_FIELDS} | {"speed": moon_speed},
        "sun": {f: 0.0 for f in ALL_FIELDS} | {"speed": sun_speed},
        "mars": {f: 0.0 for f in ALL_FIELDS} | {"speed": mars_speed},
    }


def test_expand_globs_expands_body_wildcard():
    expanded = expand_globs(["moon.*"], bodies=["moon", "sun", "mars"])
    assert set(expanded) == {f"moon.{f}" for f in ALL_FIELDS}


def test_expand_globs_passes_through_explicit_keys():
    expanded = expand_globs(["moon.speed", "sun.start_pos"], bodies=["moon", "sun"])
    assert set(expanded) == {"moon.speed", "sun.start_pos"}


def test_expand_globs_combines_glob_and_explicit():
    expanded = expand_globs(["moon.*", "sun.speed"], bodies=["moon", "sun"])
    assert "moon.orbit_radius" in expanded
    assert "moon.speed" in expanded
    assert "sun.speed" in expanded
    assert "sun.start_pos" not in expanded


def test_check_diff_accepts_change_inside_allowlist():
    baseline = _params(moon_speed=83.0)
    current = _params(moon_speed=83.5)
    # should not raise
    check_diff_against_allowlist(
        current, baseline, allowlist_globs=["moon.*"], known_bodies=list(baseline.keys())
    )


def test_check_diff_rejects_change_outside_allowlist():
    baseline = _params(mars_speed=-3.34)
    current = _params(mars_speed=-3.40)
    with pytest.raises(AllowlistViolation) as exc:
        check_diff_against_allowlist(
            current, baseline, allowlist_globs=["moon.*"], known_bodies=list(baseline.keys())
        )
    assert "mars.speed" in str(exc.value)


def test_check_diff_rejects_added_key():
    baseline = _params()
    current = _params()
    current["moon"]["new_field"] = 1.0
    with pytest.raises(AllowlistViolation) as exc:
        check_diff_against_allowlist(
            current, baseline, allowlist_globs=["moon.*"], known_bodies=list(baseline.keys())
        )
    assert "added" in str(exc.value).lower()


def test_check_diff_rejects_removed_key():
    baseline = _params()
    current = _params()
    del current["moon"]["start_pos"]
    with pytest.raises(AllowlistViolation) as exc:
        check_diff_against_allowlist(
            current, baseline, allowlist_globs=["moon.*"], known_bodies=list(baseline.keys())
        )
    assert "removed" in str(exc.value).lower()


def test_check_diff_rejects_added_body():
    baseline = _params()
    current = _params()
    current["pluto"] = {f: 0.0 for f in ALL_FIELDS}
    with pytest.raises(AllowlistViolation):
        check_diff_against_allowlist(
            current, baseline, allowlist_globs=["moon.*"], known_bodies=list(baseline.keys())
        )


def test_check_diff_rejects_non_numeric_value():
    baseline = _params()
    current = _params()
    current["moon"]["speed"] = "fast"
    with pytest.raises(AllowlistViolation) as exc:
        check_diff_against_allowlist(
            current, baseline, allowlist_globs=["moon.*"], known_bodies=list(baseline.keys())
        )
    assert "numeric" in str(exc.value).lower() or "number" in str(exc.value).lower()
```

- [ ] **Step 2: Run to verify they fail**

```bash
source tychos_skyfield/.venv/bin/activate && PYTHONPATH=tychos_skyfield:tests:. python -m pytest tests/research/test_allowlist.py -v
```
Expected: ImportError on `server.research.allowlist`.

- [ ] **Step 3: Implement `server/research/allowlist.py`**

```python
"""Allowlist parsing, glob expansion, and diff validation."""
from numbers import Real


class AllowlistViolation(Exception):
    """Raised when current.json contains a change forbidden by the allowlist."""


_ORBIT_FIELDS = (
    "orbit_radius",
    "orbit_center_a",
    "orbit_center_b",
    "orbit_center_c",
    "orbit_tilt_a",
    "orbit_tilt_b",
    "start_pos",
    "speed",
)


def expand_globs(globs: list[str], bodies: list[str]) -> set[str]:
    """Expand `body.*` patterns to concrete `body.field` keys.

    `globs` is a list of strings like 'moon.*' or 'sun.speed'.
    `bodies` is the list of known body names from baseline params.
    Returns a set of fully-qualified `body.field` strings.
    """
    out: set[str] = set()
    for g in globs:
        if "." not in g:
            raise ValueError(f"Allowlist entry must be 'body.field' or 'body.*': {g!r}")
        body, field = g.split(".", 1)
        if body not in bodies:
            # Silently ignore unknown bodies — allowlist may be reused across param sets.
            continue
        if field == "*":
            for f in _ORBIT_FIELDS:
                out.add(f"{body}.{f}")
        else:
            out.add(f"{body}.{field}")
    return out


def check_diff_against_allowlist(
    current: dict,
    baseline: dict,
    allowlist_globs: list[str],
    known_bodies: list[str],
) -> None:
    """Raise AllowlistViolation if current diverges from baseline outside the allowlist.

    Validates:
      - No added or removed bodies.
      - No added or removed keys within any body.
      - All allowlisted values are numeric.
      - Any value that differs from baseline is in the allowlist.
    """
    allowed = expand_globs(allowlist_globs, known_bodies)

    base_bodies = set(baseline.keys())
    cur_bodies = set(current.keys())
    if cur_bodies - base_bodies:
        raise AllowlistViolation(
            f"Bodies added to current.json that don't exist in baseline: "
            f"{sorted(cur_bodies - base_bodies)}"
        )
    if base_bodies - cur_bodies:
        raise AllowlistViolation(
            f"Bodies removed from current.json: {sorted(base_bodies - cur_bodies)}"
        )

    for body in sorted(base_bodies):
        base_fields = set(baseline[body].keys())
        cur_fields = set(current[body].keys())
        added = cur_fields - base_fields
        removed = base_fields - cur_fields
        if added:
            raise AllowlistViolation(
                f"Fields added to {body}: {sorted(added)}"
            )
        if removed:
            raise AllowlistViolation(
                f"Fields removed from {body}: {sorted(removed)}"
            )

        for field in sorted(base_fields):
            key = f"{body}.{field}"
            base_val = baseline[body][field]
            cur_val = current[body][field]

            if cur_val != base_val:
                if key not in allowed:
                    raise AllowlistViolation(
                        f"Disallowed change to {key}: "
                        f"baseline={base_val!r} current={cur_val!r}. "
                        f"Add it to the allowlist in program.md if intended."
                    )
                if not isinstance(cur_val, Real) or isinstance(cur_val, bool):
                    raise AllowlistViolation(
                        f"{key} must be numeric, got {type(cur_val).__name__}: {cur_val!r}"
                    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
source tychos_skyfield/.venv/bin/activate && PYTHONPATH=tychos_skyfield:tests:. python -m pytest tests/research/test_allowlist.py -v
```
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add server/research/allowlist.py tests/research/test_allowlist.py
git commit -m "feat(research): allowlist parsing, glob expansion, diff validation"
```

---

## Task 3: Objective computation

**Files:**
- Create: `server/research/objective.py`
- Create: `tests/research/test_objective.py`

- [ ] **Step 1: Write failing tests**

`tests/research/test_objective.py`:
```python
import pytest

from server.research.objective import compute_objective, EmptyResults


def _row(timing_offset_min, separation_arcmin=10.0, detected=1):
    return {
        "timing_offset_min": timing_offset_min,
        "min_separation_arcmin": separation_arcmin,
        "detected": detected,
    }


def test_objective_is_mean_abs_timing_offset():
    rows = [_row(2.0), _row(-4.0), _row(6.0)]
    assert compute_objective(rows) == pytest.approx((2 + 4 + 6) / 3)


def test_objective_handles_zero_offsets():
    rows = [_row(0.0), _row(0.0)]
    assert compute_objective(rows) == 0.0


def test_objective_raises_on_empty_results():
    with pytest.raises(EmptyResults):
        compute_objective([])


def test_objective_treats_negative_and_positive_symmetrically():
    a = compute_objective([_row(5.0)])
    b = compute_objective([_row(-5.0)])
    assert a == b == 5.0
```

- [ ] **Step 2: Run to verify they fail**

```bash
source tychos_skyfield/.venv/bin/activate && PYTHONPATH=tychos_skyfield:tests:. python -m pytest tests/research/test_objective.py -v
```
Expected: ImportError.

- [ ] **Step 3: Implement `server/research/objective.py`**

```python
"""Objective function for autoresearch iterations.

The single number the agent minimizes: mean absolute timing offset (in minutes)
across the result rows of one scan. Lower is better.
"""


class EmptyResults(ValueError):
    """Raised when compute_objective is called with no results — likely a bug."""


def compute_objective(results: list[dict]) -> float:
    """Return mean(|timing_offset_min|) across results.

    Raises EmptyResults if `results` is empty (silent zero would mask bugs).
    """
    if not results:
        raise EmptyResults(
            "compute_objective called with empty results — "
            "the scan returned nothing, which usually means an empty subset or scan failure."
        )
    total = sum(abs(r["timing_offset_min"]) for r in results)
    return total / len(results)


def aux_stats(results: list[dict]) -> dict:
    """Auxiliary stats printed alongside the objective for the agent's context.

    Not used in the optimization decision — purely informational.
    """
    if not results:
        return {"mean_separation_arcmin": None, "n_detected": 0, "n_total": 0}
    n_total = len(results)
    n_detected = sum(1 for r in results if r.get("detected"))
    mean_sep = sum(r["min_separation_arcmin"] for r in results) / n_total
    return {
        "mean_separation_arcmin": round(mean_sep, 3),
        "n_detected": n_detected,
        "n_total": n_total,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
source tychos_skyfield/.venv/bin/activate && PYTHONPATH=tychos_skyfield:tests:. python -m pytest tests/research/test_objective.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add server/research/objective.py tests/research/test_objective.py
git commit -m "feat(research): objective = mean(|timing_offset_min|) + aux stats"
```

---

## Task 4: Subset selection

**Files:**
- Create: `server/research/subset.py`
- Create: `tests/research/test_subset.py`

**Context for the engineer:** Eclipse rows look like `{"julian_day_tt": float, "date": str, "type": str, "magnitude": float}`. The `type` values for solar are `"total" | "annular" | "partial" | "hybrid"` and for lunar are `"total" | "partial" | "penumbral"`. The `julian_day_tt` is a Julian Date in TT — a monotonically-ish increasing float as you walk through history.

- [ ] **Step 1: Write failing tests**

`tests/research/test_subset.py`:
```python
from server.research.subset import select_subset


def _eclipse(jd, type_, mag=1.0):
    return {"julian_day_tt": jd, "date": f"jd-{jd}", "type": type_, "magnitude": mag}


def _spread_catalog(n=200):
    """Build a synthetic catalog spanning JDs 2000000..2200000 with mixed types."""
    types = ["total", "partial", "annular"]
    return [
        _eclipse(2000000 + i * 1000, types[i % 3])
        for i in range(n)
    ]


def test_subset_size_matches_request():
    cat = _spread_catalog()
    out = select_subset(cat, n=25, seed=42)
    assert len(out) == 25


def test_subset_is_deterministic():
    cat = _spread_catalog()
    a = select_subset(cat, n=25, seed=42)
    b = select_subset(cat, n=25, seed=42)
    assert [r["julian_day_tt"] for r in a] == [r["julian_day_tt"] for r in b]


def test_subset_changes_with_seed():
    cat = _spread_catalog()
    a = select_subset(cat, n=25, seed=42)
    b = select_subset(cat, n=25, seed=99)
    assert [r["julian_day_tt"] for r in a] != [r["julian_day_tt"] for r in b]


def test_subset_stratifies_by_date():
    """Each subset element should come from a distinct equal-width JD bucket."""
    cat = _spread_catalog()
    out = select_subset(cat, n=10, seed=42)
    jd_min = min(r["julian_day_tt"] for r in cat)
    jd_max = max(r["julian_day_tt"] for r in cat)
    bucket_width = (jd_max - jd_min) / 10
    bucket_indices = {
        min(int((r["julian_day_tt"] - jd_min) / bucket_width), 9)
        for r in out
    }
    assert len(bucket_indices) == 10  # one per bucket


def test_subset_smaller_than_n_returns_all():
    cat = _spread_catalog(n=5)
    out = select_subset(cat, n=25, seed=42)
    assert len(out) == 5


def test_subset_sorted_by_jd():
    cat = _spread_catalog()
    out = select_subset(cat, n=25, seed=42)
    jds = [r["julian_day_tt"] for r in out]
    assert jds == sorted(jds)
```

- [ ] **Step 2: Run to verify they fail**

```bash
source tychos_skyfield/.venv/bin/activate && PYTHONPATH=tychos_skyfield:tests:. python -m pytest tests/research/test_subset.py -v
```
Expected: ImportError.

- [ ] **Step 3: Implement `server/research/subset.py`**

```python
"""Deterministic stratified subset selection for research jobs."""
import random

from server.db import get_db


def select_subset(catalog: list[dict], n: int, seed: int) -> list[dict]:
    """Pick `n` eclipses from `catalog` using deterministic stratified sampling.

    Strategy:
      1. If catalog has <= n entries, return all of them sorted by JD.
      2. Sort catalog by julian_day_tt.
      3. Divide the JD range into `n` equal-width buckets.
      4. Within each bucket, prefer type-diversity by round-robin: pick the
         entry whose type has been picked least so far; tie-break with the
         seeded RNG.
      5. If a bucket is empty, fall back to picking the nearest unpicked
         entry from an adjacent bucket.
      6. Return the picked entries sorted by JD.

    Always deterministic for a given (catalog contents, n, seed).
    """
    if not catalog:
        return []
    cat = sorted(catalog, key=lambda r: r["julian_day_tt"])
    if len(cat) <= n:
        return cat

    rng = random.Random(seed)

    jd_min = cat[0]["julian_day_tt"]
    jd_max = cat[-1]["julian_day_tt"]
    span = jd_max - jd_min
    if span == 0:
        # All same JD — degenerate; just sample n with the rng.
        return sorted(rng.sample(cat, n), key=lambda r: r["julian_day_tt"])

    # Bucket assignments
    buckets: list[list[dict]] = [[] for _ in range(n)]
    for r in cat:
        idx = int((r["julian_day_tt"] - jd_min) / span * n)
        if idx >= n:
            idx = n - 1
        buckets[idx].append(r)

    type_counts: dict[str, int] = {}
    picked: list[dict] = []

    def _pick_from(candidates: list[dict]) -> dict:
        """Pick the candidate whose type has been used least; tie-break by rng."""
        if not candidates:
            raise RuntimeError("internal: _pick_from called with empty list")
        min_count = min(type_counts.get(c["type"], 0) for c in candidates)
        best = [c for c in candidates if type_counts.get(c["type"], 0) == min_count]
        return rng.choice(best)

    for i in range(n):
        if buckets[i]:
            chosen = _pick_from(buckets[i])
            buckets[i].remove(chosen)
        else:
            # Fall back: walk outward to find the nearest non-empty bucket.
            chosen = None
            for offset in range(1, n):
                left = i - offset
                right = i + offset
                if left >= 0 and buckets[left]:
                    chosen = _pick_from(buckets[left])
                    buckets[left].remove(chosen)
                    break
                if right < n and buckets[right]:
                    chosen = _pick_from(buckets[right])
                    buckets[right].remove(chosen)
                    break
            if chosen is None:
                break  # exhausted catalog
        picked.append(chosen)
        type_counts[chosen["type"]] = type_counts.get(chosen["type"], 0) + 1

    return sorted(picked, key=lambda r: r["julian_day_tt"])


def load_eclipses_for_dataset(dataset_slug: str) -> list[dict]:
    """Load all eclipse_catalog rows for a dataset slug from the live DB.

    `dataset_slug` is 'solar_eclipse' or 'lunar_eclipse'. Returns rows in
    the same shape scanner.load_eclipse_catalog uses.
    """
    with get_db() as conn:
        row = conn.execute(
            "SELECT id FROM datasets WHERE slug = ?", (dataset_slug,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Unknown dataset slug: {dataset_slug}")
        dataset_id = row["id"]
        rows = conn.execute(
            "SELECT julian_day_tt, date, type, magnitude "
            "FROM eclipse_catalog WHERE dataset_id = ? ORDER BY julian_day_tt",
            (dataset_id,),
        ).fetchall()
    return [dict(r) for r in rows]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
source tychos_skyfield/.venv/bin/activate && PYTHONPATH=tychos_skyfield:tests:. python -m pytest tests/research/test_subset.py -v
```
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add server/research/subset.py tests/research/test_subset.py
git commit -m "feat(research): deterministic stratified subset selection"
```

---

## Task 5: Sandbox utilities (load, hash, log)

**Files:**
- Create: `server/research/sandbox.py`
- Create: `tests/research/test_sandbox.py`

- [ ] **Step 1: Write failing tests**

`tests/research/test_sandbox.py`:
```python
import json
from pathlib import Path

import pytest

from server.research.sandbox import (
    JobPaths,
    params_hash,
    append_log,
    read_log_tail,
    load_json,
    write_json,
)


def test_job_paths_resolves_files(tmp_path: Path):
    paths = JobPaths(root=tmp_path / "myjob")
    assert paths.root == tmp_path / "myjob"
    assert paths.current_json == tmp_path / "myjob" / "current.json"
    assert paths.baseline_json == tmp_path / "myjob" / "baseline.json"
    assert paths.subset_json == tmp_path / "myjob" / "subset.json"
    assert paths.program_md == tmp_path / "myjob" / "program.md"
    assert paths.log_jsonl == tmp_path / "myjob" / "log.jsonl"


def test_params_hash_is_stable_across_dict_order():
    a = {"moon": {"speed": 83.0, "start_pos": 261.2}}
    b = {"moon": {"start_pos": 261.2, "speed": 83.0}}
    assert params_hash(a) == params_hash(b)


def test_params_hash_changes_with_value():
    a = {"moon": {"speed": 83.0}}
    b = {"moon": {"speed": 83.5}}
    assert params_hash(a) != params_hash(b)


def test_append_and_read_log_tail(tmp_path: Path):
    log = tmp_path / "log.jsonl"
    append_log(log, {"iter": 1, "objective": 5.0})
    append_log(log, {"iter": 2, "objective": 4.5})
    append_log(log, {"iter": 3, "objective": 4.0})
    tail = read_log_tail(log, n=2)
    assert len(tail) == 2
    assert tail[0]["iter"] == 2
    assert tail[1]["iter"] == 3


def test_read_log_tail_handles_missing_file(tmp_path: Path):
    assert read_log_tail(tmp_path / "missing.jsonl", n=5) == []


def test_write_and_load_json_roundtrip(tmp_path: Path):
    p = tmp_path / "x.json"
    write_json(p, {"a": 1, "b": [1, 2, 3]})
    assert load_json(p) == {"a": 1, "b": [1, 2, 3]}


def test_load_json_missing_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_json(tmp_path / "nope.json")
```

- [ ] **Step 2: Run to verify they fail**

```bash
source tychos_skyfield/.venv/bin/activate && PYTHONPATH=tychos_skyfield:tests:. python -m pytest tests/research/test_sandbox.py -v
```
Expected: ImportError.

- [ ] **Step 3: Implement `server/research/sandbox.py`**

```python
"""Sandbox directory layout, JSON I/O, content hashing, and JSONL log writer."""
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

PARAMS_RESEARCH_ROOT = Path(__file__).parent.parent.parent / "params" / "research"


@dataclass
class JobPaths:
    """Resolved file paths for a single research job."""
    root: Path

    @property
    def current_json(self) -> Path:
        return self.root / "current.json"

    @property
    def baseline_json(self) -> Path:
        return self.root / "baseline.json"

    @property
    def subset_json(self) -> Path:
        return self.root / "subset.json"

    @property
    def program_md(self) -> Path:
        return self.root / "program.md"

    @property
    def log_jsonl(self) -> Path:
        return self.root / "log.jsonl"

    @classmethod
    def for_job(cls, job_name: str) -> "JobPaths":
        return cls(root=PARAMS_RESEARCH_ROOT / job_name)


def load_json(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")


def params_hash(params: dict) -> str:
    """Stable content hash over the params dict (order-independent)."""
    canonical = json.dumps(params, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def append_log(log_path: Path, entry: dict) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a") as f:
        f.write(json.dumps(entry) + "\n")


def read_log_tail(log_path: Path, n: int) -> list[dict]:
    if not log_path.exists():
        return []
    with open(log_path) as f:
        lines = [line for line in f if line.strip()]
    return [json.loads(line) for line in lines[-n:]]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
source tychos_skyfield/.venv/bin/activate && PYTHONPATH=tychos_skyfield:tests:. python -m pytest tests/research/test_sandbox.py -v
```
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add server/research/sandbox.py tests/research/test_sandbox.py
git commit -m "feat(research): sandbox dataclass + JSON/JSONL/hash helpers"
```

---

## Task 6: program.md template + frontmatter parser

**Files:**
- Create: `server/research/templates/program.md.tmpl`
- Create: `server/research/program_md.py`
- Create: `tests/research/test_program_md.py`

- [ ] **Step 1: Create the template file**

`server/research/templates/program.md.tmpl`:
```markdown
---
job: {job_name}
dataset: {dataset_slug}
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
Lower `mean(|timing_offset_min|)` on the {dataset_slug} subset by editing
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
- **Only edit `current.json`.** Never touch `baseline.json`, `subset.json`, or any other file.
- **Only edit allowlisted keys.** The CLI will hard-fail if you don't.
- **One change at a time** when possible — easier to attribute wins.

## Background
TODO: fill in physics context — what timing_offset_min means, how moon.speed
relates to the lunar sidereal rate, how earth.speed affects geocentric apparent
motion, which deferent fields shape the lunar epicycle, etc. This section is
the main lever for making the agent productive; iterate on it over time.
```

- [ ] **Step 2: Write failing tests**

`tests/research/test_program_md.py`:
```python
import pytest

from server.research.program_md import parse_frontmatter, render_template


def test_parse_frontmatter_extracts_allowlist():
    md = """---
job: test-1
dataset: solar_eclipse
base_param_version: v1-original/v2
allowlist:
  - moon.*
  - sun.speed
---

# body
"""
    fm = parse_frontmatter(md)
    assert fm["job"] == "test-1"
    assert fm["dataset"] == "solar_eclipse"
    assert fm["base_param_version"] == "v1-original/v2"
    assert fm["allowlist"] == ["moon.*", "sun.speed"]


def test_parse_frontmatter_missing_block_raises():
    with pytest.raises(ValueError):
        parse_frontmatter("# no frontmatter here\n")


def test_render_template_substitutes_placeholders():
    out = render_template(
        job_name="solar-fit-001",
        dataset_slug="solar_eclipse",
        base_param_version="v1-original/v2",
    )
    assert "job: solar-fit-001" in out
    assert "dataset: solar_eclipse" in out
    assert "base_param_version: v1-original/v2" in out
    assert "{job_name}" not in out
    assert "{dataset_slug}" not in out


def test_render_then_parse_roundtrip():
    out = render_template(
        job_name="lunar-fit-001",
        dataset_slug="lunar_eclipse",
        base_param_version="v1-original/v2",
    )
    fm = parse_frontmatter(out)
    assert fm["job"] == "lunar-fit-001"
    assert fm["dataset"] == "lunar_eclipse"
    assert "moon.*" in fm["allowlist"]
```

- [ ] **Step 3: Run to verify they fail**

```bash
source tychos_skyfield/.venv/bin/activate && PYTHONPATH=tychos_skyfield:tests:. python -m pytest tests/research/test_program_md.py -v
```
Expected: ImportError.

- [ ] **Step 4: Implement `server/research/program_md.py`**

This file deliberately does NOT depend on PyYAML — the frontmatter we parse is
intentionally simple (scalars + a single list of strings) and we want zero new
dependencies. We hand-parse it.

```python
"""program.md template rendering and frontmatter parsing.

We hand-parse a small subset of YAML to avoid adding PyYAML as a dependency:
  - Scalar key/value pairs: `key: value`
  - One list-of-strings: `allowlist:` followed by `  - item` lines
"""
from pathlib import Path

_TEMPLATE_PATH = Path(__file__).parent / "templates" / "program.md.tmpl"


def render_template(*, job_name: str, dataset_slug: str, base_param_version: str) -> str:
    raw = _TEMPLATE_PATH.read_text()
    return raw.format(
        job_name=job_name,
        dataset_slug=dataset_slug,
        base_param_version=base_param_version,
    )


def parse_frontmatter(md: str) -> dict:
    """Extract the YAML-ish frontmatter block delimited by `---` lines.

    Returns a dict with scalar values plus an `allowlist` list. Raises
    ValueError if no frontmatter is present.
    """
    lines = md.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("program.md must start with a '---' frontmatter block")
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break
    if end_idx is None:
        raise ValueError("Unterminated frontmatter block (missing closing ---)")

    body_lines = lines[1:end_idx]
    out: dict = {}
    i = 0
    while i < len(body_lines):
        line = body_lines[i]
        if not line.strip():
            i += 1
            continue
        if ":" not in line:
            raise ValueError(f"Malformed frontmatter line: {line!r}")
        key, _, rest = line.partition(":")
        key = key.strip()
        rest = rest.strip()
        if rest == "":
            # List follows
            items: list[str] = []
            j = i + 1
            while j < len(body_lines):
                next_line = body_lines[j]
                stripped = next_line.lstrip()
                if stripped.startswith("- "):
                    items.append(stripped[2:].strip())
                    j += 1
                elif not next_line.strip():
                    j += 1
                else:
                    break
            out[key] = items
            i = j
        else:
            out[key] = rest
            i += 1
    return out
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
source tychos_skyfield/.venv/bin/activate && PYTHONPATH=tychos_skyfield:tests:. python -m pytest tests/research/test_program_md.py -v
```
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add server/research/templates/ server/research/program_md.py tests/research/test_program_md.py
git commit -m "feat(research): program.md template + frontmatter parser"
```

---

## Task 7: `init` command

**Files:**
- Modify: `server/research/cli.py`

**Context for the engineer:** Param versions live in `params/<version>/v<N>.json`
where `<version>` looks like `v1-original` and the file is e.g. `v2.json`. The
JSON has a top-level `params` key wrapping the body dict. So `--base v1-original/v2`
should resolve to `params/v1-original/v2.json` and we read its `params` field.

- [ ] **Step 1: Reuse existing param-loading helper if present**

Run:
```bash
source tychos_skyfield/.venv/bin/activate && PYTHONPATH=tychos_skyfield:tests:. python -c "from server.params_store import load_param_version; help(load_param_version)" 2>&1 | head -20
```

If a helper exists, use it. If not, the implementation below reads the file
directly. (Either is fine — prefer the helper if it exists.)

- [ ] **Step 2: Implement `cmd_init` in `server/research/cli.py`**

Replace the stub `cmd_init` with:

```python
"""CLI command implementations for `python -m server.research`."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from server.research.sandbox import (
    JobPaths,
    write_json,
    load_json,
    append_log,
    params_hash,
    read_log_tail,
)
from server.research.program_md import render_template, parse_frontmatter
from server.research.subset import select_subset, load_eclipses_for_dataset
from server.research.allowlist import (
    check_diff_against_allowlist,
    AllowlistViolation,
)
from server.research.objective import compute_objective, aux_stats, EmptyResults

# Map short --dataset arg to the dataset slug used in the DB and in scanner dispatch.
_DATASET_SLUG = {
    "solar": "solar_eclipse",
    "lunar": "lunar_eclipse",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_base_params(base_arg: str) -> dict:
    """Load the params dict from a versioned param file.

    `base_arg` is like 'v1-original/v2'. Resolves to params/<dir>/<file>.json.
    """
    repo_root = Path(__file__).parent.parent.parent
    parts = base_arg.split("/")
    if len(parts) != 2:
        raise ValueError(f"--base must be like 'v1-original/v2', got {base_arg!r}")
    version_dir, version_file = parts
    path = repo_root / "params" / version_dir / f"{version_file}.json"
    if not path.exists():
        raise FileNotFoundError(f"Base param version not found: {path}")
    raw = load_json(path)
    if "params" not in raw:
        raise ValueError(f"Param file {path} missing top-level 'params' key")
    return raw["params"]


def cmd_init(args) -> int:
    paths = JobPaths.for_job(args.job)
    if paths.root.exists():
        print(f"error: job directory already exists: {paths.root}", file=sys.stderr)
        return 2

    dataset_slug = _DATASET_SLUG[args.dataset]
    base_params = _resolve_base_params(args.base)

    paths.root.mkdir(parents=True, exist_ok=False)

    # baseline.json + current.json — identical at init time
    write_json(paths.baseline_json, base_params)
    write_json(paths.current_json, base_params)

    # subset.json — frozen stratified pick
    catalog = load_eclipses_for_dataset(dataset_slug)
    if not catalog:
        print(f"error: no eclipses found for dataset {dataset_slug}", file=sys.stderr)
        return 3
    chosen = select_subset(catalog, n=args.subset_size, seed=args.seed)
    write_json(paths.subset_json, {
        "dataset_slug": dataset_slug,
        "n_requested": args.subset_size,
        "seed": args.seed,
        "selected_at": _now_iso(),
        "events": chosen,
    })

    # program.md — render from template
    paths.program_md.write_text(
        render_template(
            job_name=args.job,
            dataset_slug=dataset_slug,
            base_param_version=args.base,
        )
    )

    # log.jsonl — empty file (touch)
    paths.log_jsonl.touch()

    print(f"Initialized job at {paths.root}")
    print(f"  dataset: {dataset_slug}")
    print(f"  base:    {args.base}")
    print(f"  subset:  {len(chosen)} events (seed={args.seed})")
    print()
    print(f"Next: open `claude` in this repo and point it at:")
    print(f"  {paths.program_md}")
    return 0


def cmd_iterate(args) -> int:
    raise NotImplementedError


def cmd_validate(args) -> int:
    raise NotImplementedError
```

- [ ] **Step 3: Manual smoke test of `init`**

Run:
```bash
source tychos_skyfield/.venv/bin/activate && \
  PYTHONPATH=tychos_skyfield:tests:. python -m server.research init plan-test --base v1-original/v2 --dataset solar
```

Expected: Creates `params/research/plan-test/` with all 5 files. Prints
"Initialized job at ...". Exits 0.

Verify with:
```bash
ls params/research/plan-test/
```
Expected output:
```
baseline.json   current.json   log.jsonl   program.md   subset.json
```

- [ ] **Step 4: Verify init is idempotent-failing**

Run the same `init` command again. Expected: prints
`error: job directory already exists`, exits 2.

Then clean up:
```bash
rm -rf params/research/plan-test
```

- [ ] **Step 5: Commit**

```bash
git add server/research/cli.py
git commit -m "feat(research): implement `init` command"
```

---

## Task 8: `iterate` command

**Files:**
- Modify: `server/research/cli.py`

**Context for the engineer:** The existing scanner functions live at
`server/services/scanner.py::scan_solar_eclipses` and `scan_lunar_eclipses`.
Both take `(params: dict, eclipses: list[dict])` and return a list of result
rows including `timing_offset_min`. We call them directly with the subset
loaded from `subset.json` — no DB read needed during `iterate`.

- [ ] **Step 1: Replace `cmd_iterate` stub with the real implementation**

In `server/research/cli.py`, replace:

```python
def cmd_iterate(args) -> int:
    raise NotImplementedError
```

with:

```python
def _load_job_state(job_name: str):
    """Load all sandbox files needed for iterate/validate. Returns a tuple."""
    paths = JobPaths.for_job(job_name)
    if not paths.root.exists():
        raise FileNotFoundError(
            f"Job directory not found: {paths.root}. Run `init` first."
        )
    current = load_json(paths.current_json)
    baseline = load_json(paths.baseline_json)
    program_md = paths.program_md.read_text()
    frontmatter = parse_frontmatter(program_md)
    subset_blob = load_json(paths.subset_json)
    return paths, current, baseline, frontmatter, subset_blob


def _run_scan(dataset_slug: str, params: dict, eclipses: list[dict]) -> list[dict]:
    """Dispatch to the right scanner for the dataset."""
    from server.services.scanner import scan_solar_eclipses, scan_lunar_eclipses
    if dataset_slug == "solar_eclipse":
        return scan_solar_eclipses(params, eclipses)
    if dataset_slug == "lunar_eclipse":
        return scan_lunar_eclipses(params, eclipses)
    raise ValueError(f"Unknown dataset_slug: {dataset_slug}")


def _next_iter_number(log_path) -> int:
    tail = read_log_tail(log_path, n=1)
    if not tail:
        return 1
    return int(tail[0].get("iter", 0)) + 1


def cmd_iterate(args) -> int:
    try:
        paths, current, baseline, frontmatter, subset_blob = _load_job_state(args.job)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    # Guardrail: allowlist diff
    try:
        check_diff_against_allowlist(
            current,
            baseline,
            allowlist_globs=frontmatter.get("allowlist", []),
            known_bodies=list(baseline.keys()),
        )
    except AllowlistViolation as e:
        print(f"error: allowlist violation: {e}", file=sys.stderr)
        return 4

    # Guardrail: hash dedup
    h = params_hash(current)
    tail = read_log_tail(paths.log_jsonl, n=1)
    if tail and tail[0].get("params_hash") == h and tail[0].get("kind") == "iterate":
        cached = tail[0]
        print(f"objective: {cached['objective']}")
        print(f"mean_separation_arcmin: {cached.get('mean_separation_arcmin')}")
        print(f"detected: {cached.get('n_detected')}/{cached.get('n_total')}")
        print("(cached — current.json identical to last iterate)")
        return 0

    dataset_slug = subset_blob["dataset_slug"]
    eclipses = subset_blob["events"]

    try:
        results = _run_scan(dataset_slug, current, eclipses)
        objective = compute_objective(results)
    except EmptyResults as e:
        print(f"error: {e}", file=sys.stderr)
        return 5

    aux = aux_stats(results)

    entry = {
        "iter": _next_iter_number(paths.log_jsonl),
        "ts": _now_iso(),
        "kind": "iterate",
        "params_hash": h,
        "objective": round(objective, 4),
        **aux,
    }
    append_log(paths.log_jsonl, entry)

    print(f"objective: {entry['objective']}")
    print(f"mean_separation_arcmin: {aux['mean_separation_arcmin']}")
    print(f"detected: {aux['n_detected']}/{aux['n_total']}")
    return 0
```

- [ ] **Step 2: Manual smoke test of `iterate`**

```bash
source tychos_skyfield/.venv/bin/activate && \
  PYTHONPATH=tychos_skyfield:tests:. python -m server.research init smoke-iter --base v1-original/v2 --dataset solar && \
  PYTHONPATH=tychos_skyfield:tests:. python -m server.research iterate smoke-iter
```

Expected: First command creates the dir. Second prints something like:
```
objective: 12.34
mean_separation_arcmin: 28.7
detected: 22/25
```
and exits 0. `params/research/smoke-iter/log.jsonl` has one line.

- [ ] **Step 3: Verify hash dedup**

Run `iterate` again immediately:
```bash
PYTHONPATH=tychos_skyfield:tests:. python -m server.research iterate smoke-iter
```
Expected: Same numbers, with `(cached — current.json identical to last iterate)`
on the last line. `log.jsonl` is unchanged (still one line).

- [ ] **Step 4: Verify allowlist guardrail fires**

Edit `params/research/smoke-iter/current.json` and change `mars.speed` (which
is NOT in the default allowlist) to a different value. Run iterate. Expected:
non-zero exit, error message naming `mars.speed`.

Revert the edit. Then clean up:
```bash
rm -rf params/research/smoke-iter
```

- [ ] **Step 5: Commit**

```bash
git add server/research/cli.py
git commit -m "feat(research): implement `iterate` command with guardrails"
```

---

## Task 9: `validate` command

**Files:**
- Modify: `server/research/cli.py`

- [ ] **Step 1: Replace `cmd_validate` stub**

In `server/research/cli.py`, replace:

```python
def cmd_validate(args) -> int:
    raise NotImplementedError
```

with:

```python
def cmd_validate(args) -> int:
    try:
        paths, current, baseline, frontmatter, subset_blob = _load_job_state(args.job)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    # Same guardrails as iterate
    try:
        check_diff_against_allowlist(
            current,
            baseline,
            allowlist_globs=frontmatter.get("allowlist", []),
            known_bodies=list(baseline.keys()),
        )
    except AllowlistViolation as e:
        print(f"error: allowlist violation: {e}", file=sys.stderr)
        return 4

    dataset_slug = subset_blob["dataset_slug"]
    full_catalog = load_eclipses_for_dataset(dataset_slug)
    if not full_catalog:
        print(f"error: no eclipses found for dataset {dataset_slug}", file=sys.stderr)
        return 3

    try:
        results = _run_scan(dataset_slug, current, full_catalog)
        objective = compute_objective(results)
    except EmptyResults as e:
        print(f"error: {e}", file=sys.stderr)
        return 5

    aux = aux_stats(results)

    entry = {
        "iter": _next_iter_number(paths.log_jsonl),
        "ts": _now_iso(),
        "kind": "validate",
        "params_hash": params_hash(current),
        "validation_objective": round(objective, 4),
        **aux,
    }
    append_log(paths.log_jsonl, entry)

    print(f"validation_objective: {entry['validation_objective']}")
    print(f"mean_separation_arcmin: {aux['mean_separation_arcmin']}")
    print(f"detected: {aux['n_detected']}/{aux['n_total']}")
    return 0
```

- [ ] **Step 2: Manual smoke test**

```bash
source tychos_skyfield/.venv/bin/activate && \
  PYTHONPATH=tychos_skyfield:tests:. python -m server.research init smoke-val --base v1-original/v2 --dataset solar && \
  PYTHONPATH=tychos_skyfield:tests:. python -m server.research validate smoke-val
```

Expected: Prints `validation_objective: <number>`, runs against the full
catalog (will take noticeably longer than `iterate`). `log.jsonl` has one
entry with `kind: validate`. Exits 0.

Clean up:
```bash
rm -rf params/research/smoke-val
```

- [ ] **Step 3: Commit**

```bash
git add server/research/cli.py
git commit -m "feat(research): implement `validate` command (full-catalog scan)"
```

---

## Task 10: End-to-end smoke test

**Files:**
- Create: `tests/research/test_smoke.py`
- Create: `tests/research/conftest.py`

**Context for the engineer:** The smoke test must run `init` → `iterate` → `validate`
without depending on the live results DB existing. We do that by monkey-patching
`load_eclipses_for_dataset` to return a tiny fixture catalog of 3 known eclipses
that the v1-original/v2 params will detect.

- [ ] **Step 1: Write `tests/research/conftest.py`**

```python
import sys
from pathlib import Path

# Make sure tychos_skyfield, helpers, and the repo root are importable
_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_ROOT / "tychos_skyfield"))
sys.path.insert(0, str(_ROOT / "tests"))
sys.path.insert(0, str(_ROOT))


import pytest


# Three known eclipses used by the existing scanner tests — guaranteed to be
# detected by v1-original/v2 params.
_FIXTURE_ECLIPSES_SOLAR = [
    {
        "julian_day_tt": 2457987.268519,
        "date": "2017-08-21T18:26:40",
        "type": "total",
        "magnitude": 1.0306,
    },
    {
        "julian_day_tt": 2459883.953472,
        "date": "2022-10-25T11:00:00",
        "type": "partial",
        "magnitude": 0.86,
    },
    {
        "julian_day_tt": 2460388.819444,
        "date": "2024-04-08T18:20:00",
        "type": "total",
        "magnitude": 1.0566,
    },
]


@pytest.fixture
def fixture_solar_eclipses():
    return list(_FIXTURE_ECLIPSES_SOLAR)


@pytest.fixture
def patched_catalog_loader(monkeypatch, fixture_solar_eclipses):
    """Replace `load_eclipses_for_dataset` so init/validate don't touch the live DB."""
    from server.research import subset as subset_mod
    from server.research import cli as cli_mod

    def _fake(slug):
        if slug == "solar_eclipse":
            return list(fixture_solar_eclipses)
        return []

    monkeypatch.setattr(subset_mod, "load_eclipses_for_dataset", _fake)
    monkeypatch.setattr(cli_mod, "load_eclipses_for_dataset", _fake)
    return _fake


@pytest.fixture
def isolated_research_root(monkeypatch, tmp_path):
    """Point JobPaths.PARAMS_RESEARCH_ROOT at a tmp dir so tests don't pollute the repo."""
    from server.research import sandbox
    fake_root = tmp_path / "research"
    monkeypatch.setattr(sandbox, "PARAMS_RESEARCH_ROOT", fake_root)
    return fake_root
```

- [ ] **Step 2: Write the smoke test**

`tests/research/test_smoke.py`:
```python
import json
from types import SimpleNamespace

from server.research import cli


def _init_args(job, base="v1-original/v2", dataset="solar"):
    return SimpleNamespace(
        job=job, base=base, dataset=dataset, subset_size=3, seed=42
    )


def _job_args(job):
    return SimpleNamespace(job=job)


def test_init_creates_all_sandbox_files(
    isolated_research_root, patched_catalog_loader, capsys
):
    rc = cli.cmd_init(_init_args("smoke-1"))
    assert rc == 0
    job_root = isolated_research_root / "smoke-1"
    assert job_root.exists()
    for name in ("baseline.json", "current.json", "subset.json", "program.md", "log.jsonl"):
        assert (job_root / name).exists(), f"missing {name}"
    # Sanity: subset has the requested 3 events
    subset = json.loads((job_root / "subset.json").read_text())
    assert len(subset["events"]) == 3


def test_iterate_prints_objective_and_logs(
    isolated_research_root, patched_catalog_loader, capsys
):
    cli.cmd_init(_init_args("smoke-2"))
    capsys.readouterr()  # discard init output

    rc = cli.cmd_iterate(_job_args("smoke-2"))
    assert rc == 0
    out = capsys.readouterr().out
    assert "objective:" in out

    log_path = isolated_research_root / "smoke-2" / "log.jsonl"
    lines = [line for line in log_path.read_text().splitlines() if line.strip()]
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["kind"] == "iterate"
    assert "objective" in entry
    assert entry["n_total"] == 3


def test_iterate_dedups_on_unchanged_params(
    isolated_research_root, patched_catalog_loader, capsys
):
    cli.cmd_init(_init_args("smoke-3"))
    capsys.readouterr()

    cli.cmd_iterate(_job_args("smoke-3"))
    capsys.readouterr()

    cli.cmd_iterate(_job_args("smoke-3"))
    out = capsys.readouterr().out
    assert "cached" in out

    log_path = isolated_research_root / "smoke-3" / "log.jsonl"
    lines = [line for line in log_path.read_text().splitlines() if line.strip()]
    assert len(lines) == 1, "second iterate should not append a new log entry"


def test_validate_prints_validation_objective_and_logs(
    isolated_research_root, patched_catalog_loader, capsys
):
    cli.cmd_init(_init_args("smoke-4"))
    capsys.readouterr()

    rc = cli.cmd_validate(_job_args("smoke-4"))
    assert rc == 0
    out = capsys.readouterr().out
    assert "validation_objective:" in out

    log_path = isolated_research_root / "smoke-4" / "log.jsonl"
    entries = [json.loads(line) for line in log_path.read_text().splitlines() if line.strip()]
    assert len(entries) == 1
    assert entries[0]["kind"] == "validate"


def test_iterate_rejects_disallowed_param_change(
    isolated_research_root, patched_catalog_loader, capsys
):
    cli.cmd_init(_init_args("smoke-5"))
    capsys.readouterr()

    # Mutate a non-allowlisted body (mars) directly in current.json
    job_root = isolated_research_root / "smoke-5"
    current = json.loads((job_root / "current.json").read_text())
    current["mars"]["speed"] = current["mars"]["speed"] + 0.001
    (job_root / "current.json").write_text(json.dumps(current, indent=2))

    rc = cli.cmd_iterate(_job_args("smoke-5"))
    assert rc == 4
    err = capsys.readouterr().err
    assert "mars.speed" in err
```

- [ ] **Step 3: Run the smoke test**

```bash
source tychos_skyfield/.venv/bin/activate && \
  PYTHONPATH=tychos_skyfield:tests:. python -m pytest tests/research/test_smoke.py -v
```
Expected: 5 passed. (`validate` test will be the slowest since it scans the
3-event fixture catalog as the "full" catalog.)

- [ ] **Step 4: Run the entire research test suite**

```bash
source tychos_skyfield/.venv/bin/activate && \
  PYTHONPATH=tychos_skyfield:tests:. python -m pytest tests/research -v
```
Expected: All tests across `test_allowlist`, `test_objective`, `test_subset`,
`test_sandbox`, `test_program_md`, and `test_smoke` pass.

- [ ] **Step 5: Run the full repo test suite to confirm no regressions**

```bash
source tychos_skyfield/.venv/bin/activate && \
  PYTHONPATH=tychos_skyfield:tests:. python -m pytest tests -v
```
Expected: All previously-passing tests still pass, plus the new ones.

- [ ] **Step 6: Commit**

```bash
git add tests/research/conftest.py tests/research/test_smoke.py
git commit -m "test(research): end-to-end smoke test for init/iterate/validate"
```

---

## Self-Review Notes

**Spec coverage check:**
- Architecture (one CLI, no DB/worker/UI changes) → Tasks 1, 7, 8, 9 ✓
- Sandbox layout (5 files in `params/research/<job>/`) → Task 7 ✓
- `init` command → Task 7 ✓
- `iterate` command (incl. allowlist + hash dedup guardrails) → Task 8 ✓
- `validate` command → Task 9 ✓
- Subset selection (deterministic stratified) → Task 4 ✓
- Objective = `mean(|timing_offset_min|)` → Task 3 ✓
- Allowlist with glob expansion → Task 2 ✓
- `program.md` template + frontmatter parser → Task 6 ✓
- `.gitignore` update → Task 1 ✓
- Unit tests for sandbox/objective/subset/allowlist → Tasks 2–6 ✓
- End-to-end smoke test → Task 10 ✓

**Out-of-scope items confirmed not implemented:** No directional separation
field, no DB schema changes, no admin UI, no worker integration, no optimizer.

**Type / name consistency check:** `JobPaths`, `params_hash`, `compute_objective`,
`select_subset`, `load_eclipses_for_dataset`, `parse_frontmatter`, `render_template`,
`check_diff_against_allowlist`, `AllowlistViolation`, `EmptyResults` — all
referenced consistently across tasks.

**Notable carry-overs:** The pre-existing `tychos_skyfield/Tests/test_skyfield_radec.py`
collection error (unrelated to this work) means tests must be run scoped to
`tests/` not from the repo root — every test command in this plan does so.
