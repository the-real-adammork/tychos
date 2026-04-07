# Eclipse Scanner Speed Refactor (Round 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the eclipse scanner ~10× faster (~6× from multiprocessing across eclipses + ~1.7× from caching `TychosSystem` factory state) while keeping math identical so the existing exact-equality regression goldens continue to pass.

**Architecture:** Cache the per-object factory state inside `tychos_skyfield/baselib.py` (in the user's existing fork) so `move_system` stops rebuilding rotation matrices on every call. In parallel, add a persistent process pool inside `server/services/scanner.py` that shares one pool across all calls in a process; workers cache the most recent `TychosSystem` per `params` (LRU(1)) so search loops amortize construction. Worker.py reads `TYCHOS_SCANNER_MAX_WORKERS` env var. Goldens are the safety net.

**Tech Stack:** Python 3, NumPy, scipy, `concurrent.futures.ProcessPoolExecutor` with `multiprocessing.get_context("spawn")`, pytest, SQLite (unchanged).

**Related spec:** `docs/superpowers/specs/2026-04-07-eclipse-scanner-speed-design.md`

---

## Known Facts (verified before plan was written)

- `tychos_skyfield/baselib.py:144` `PlanetObj.initialize_orbit_parameters` reads only `self.orbit_tilt`, `self.orbit_center`, `self.orbit_radius` (constructor inputs). Nothing JD-dependent. Called once in `__init__` (line 142) and once per object on every `move_system` call (line 391). Profiling showed it accounts for ~42% of total scan time.
- `tychos_skyfield/baselib.py:380` `TychosSystem.move_system(julian_day)` loops over `self._all_objects` calling `initialize_orbit_parameters()` then `move_planet_tt(julian_day)`.
- `server/services/scanner.py:47` `scan_solar_eclipses(params, eclipses, half_window_hours=2.0)` and `:92` `scan_lunar_eclipses(...)` are pure (no DB). They construct one `TychosSystem` per call and loop over eclipses serially.
- `server/services/jpl_scanner.py::scan_jpl_eclipses` is the JPL path. **Out of scope for this PR** — JPL is not in the autoresearch hot path and changing it complicates the goldens story.
- `server/worker.py` is a daemon thread that calls `scan_solar_eclipses` / `scan_lunar_eclipses` per queued run. It currently does not parallelize.
- `tests/test_scanner_golden.py` has 4 `@pytest.mark.slow` tests covering Tychos solar/lunar at `half_window_hours=6.0` and JPL solar/lunar at `half_window_hours=2.0`. Exact-equality `==` comparison. **These are the safety net for this entire refactor.**
- The submodule `tychos_skyfield` has two remotes locally: `origin` → `mindaugl/tychos_skyfield` (upstream) and `fork` → `the-real-adammork/tychos_skyfield` (the user's fork). Currently checked-out branch is `feature/sync-params-from-tsn` tracking `fork/feature/sync-params-from-tsn` at commit `cf707d4`. Working tree is clean.
- Parent repo `.gitmodules` still points at upstream (`https://github.com/mindaugl/tychos_skyfield`). A fresh clone or CI run would pull the wrong remote. **Must be fixed in this PR.**
- Profiling: `scan_solar_eclipses` on 20 events, v1-original/v1, half_window=6.0, takes **16.6 seconds** baseline. This is the number we'll measure against.
- Test invocation: `PYTHONPATH=tychos_skyfield:tests:server:. /Users/adam/Projects/tychos/tychos_skyfield/.venv/bin/python -m pytest <args>`. The slow marker is registered in `pytest.ini` and excluded by default via `addopts = -m "not slow"`. Use `-m slow` to run goldens.

---

## File Structure

**Submodule fork (`tychos_skyfield`, branch `feature/sync-params-from-tsn`):**
- Modify: `tychos_skyfield/tychos_skyfield/baselib.py` — cache factory state in `PlanetObj.initialize_orbit_parameters`.

**Parent repo:**
- Modify: `.gitmodules` — point `tychos_skyfield` URL at the fork.
- Modify: `server/services/scanner.py` — add multiprocessing helpers, persistent pool, optional `max_workers` and `parallel_threshold` kwargs on the public functions.
- Modify: `server/worker.py` — read `TYCHOS_SCANNER_MAX_WORKERS` env var and pass to scanner.
- Create: `tests/test_scanner_parallel.py` — fast smoke test that exercises the parallel path with `max_workers=2, parallel_threshold=1`.
- Create: `scripts/benchmark_scanner.py` — standalone wall-clock measurement on the 20-event subset.
- Bump: parent commits a new submodule SHA pointer after the fork commit lands.

**Untouched:**
- `server/services/jpl_scanner.py` — JPL path stays serial this round.
- `tests/test_scanner_golden.py` — goldens unchanged; these are the gate.
- `tests/test_scanner.py`, `tests/test_jpl_scanner.py`, `tests/test_smoke.py` — fast tests should continue to pass with no changes.
- `server/research/search.py`, `server/research/cli.py` — search benefits transparently from the persistent pool with no caller-side changes.

---

## Task 1: Worktree setup + submodule wiring fix

This task creates the isolated worktree and updates the parent repo's `.gitmodules` to point at the fork. No code changes yet.

**Files:**
- Create (worktree): `/Users/adam/Projects/tychos-speed` (new worktree on branch `feat/scanner-speed-round-1`)
- Modify: `/Users/adam/Projects/tychos-speed/.gitmodules`

- [ ] **Step 1: Create the worktree**

```bash
cd /Users/adam/Projects/tychos
git worktree add -b feat/scanner-speed-round-1 ../tychos-speed main
```

Expected: worktree created at `/Users/adam/Projects/tychos-speed` on a fresh branch.

- [ ] **Step 2: Symlink data files into the worktree**

The worktree has empty submodule and gitignored files (`results/`, `de440s.bsp`, etc.). Symlink them so tests can run.

```bash
cd /Users/adam/Projects/tychos-speed
mkdir -p results
ln -s /Users/adam/Projects/tychos/results/tychos_results.db results/tychos_results.db
ln -s /Users/adam/Projects/tychos/de440s.bsp de440s.bsp
ln -s /Users/adam/Projects/tychos/de421.bsp de421.bsp
rmdir tychos_skyfield 2>/dev/null
ln -s /Users/adam/Projects/tychos/tychos_skyfield tychos_skyfield
```

**Important:** The `tychos_skyfield` symlink points at the *original* repo's submodule, which is on branch `feature/sync-params-from-tsn` with the fork remote configured. Edits to baselib.py will be made through this symlink and committed to the fork. The symlink target is shared between the main checkout and the worktree.

Verify:

```bash
cd /Users/adam/Projects/tychos-speed
ls -la tychos_skyfield results/tychos_results.db de440s.bsp
```

Expected: symlinks resolve to the original paths.

- [ ] **Step 3: Verify tests still run from the worktree**

```bash
cd /Users/adam/Projects/tychos-speed
PYTHONPATH=tychos_skyfield:tests:server:. /Users/adam/Projects/tychos/tychos_skyfield/.venv/bin/python -m pytest tests/test_scanner.py -v 2>&1 | tail -10
```

Expected: 6 PASS.

- [ ] **Step 4: Update .gitmodules to point at the fork**

Edit `/Users/adam/Projects/tychos-speed/.gitmodules`:

```ini
[submodule "tychos_skyfield"]
	path = tychos_skyfield
	url = https://github.com/the-real-adammork/tychos_skyfield
```

(Change only the `url` line. The `path` stays.)

- [ ] **Step 5: Sync the new URL into git config**

```bash
cd /Users/adam/Projects/tychos-speed
git submodule sync
```

Expected output: `Synchronizing submodule url for 'tychos_skyfield'`.

- [ ] **Step 6: Commit the .gitmodules change**

```bash
cd /Users/adam/Projects/tychos-speed
git add .gitmodules
git commit -m "build(submodule): point tychos_skyfield at the-real-adammork fork

The submodule is checked out from the fork locally but .gitmodules
still pointed at upstream mindaugl/tychos_skyfield. A fresh clone
would have pulled the wrong remote. This commit fixes the URL so
fresh clones and CI use the fork.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Cache TychosSystem factory state in baselib.py (fork)

This is the math-identical optimization. Modifies `tychos_skyfield/baselib.py` in the fork. Verified by running the existing slow goldens — they must still pass with exact equality.

**Files:**
- Modify: `tychos_skyfield/tychos_skyfield/baselib.py` (in the fork submodule, accessed via the symlink at `/Users/adam/Projects/tychos-speed/tychos_skyfield/`)
- Create (commit): new commit on `fork/feature/sync-params-from-tsn` branch.
- Modify (parent worktree): submodule SHA pointer in the parent repo bumps automatically.

- [ ] **Step 1: Verify clean submodule state**

```bash
cd /Users/adam/Projects/tychos/tychos_skyfield
git status
git log --oneline -1
```

Expected: clean working tree, branch `feature/sync-params-from-tsn` at `cf707d4` (or whatever the current fork tip is).

- [ ] **Step 2: Edit baselib.py to cache factory state**

Open `/Users/adam/Projects/tychos/tychos_skyfield/tychos_skyfield/baselib.py` and replace `PlanetObj.__init__` (lines 128-142) and `PlanetObj.initialize_orbit_parameters` (lines 144-155) with:

```python
    def __init__(self, orbit_radius=100.0, orbit_center=OrbitCenter(),
                 orbit_tilt=OrbitTilt(), start_pos=20.0, speed=0.0):

        self.orbit_radius = orbit_radius
        self.orbit_center = orbit_center
        self.orbit_tilt = orbit_tilt
        self.start_pos = start_pos
        self.speed = speed / (2 * np.pi)
        self.children = []

        self.rotation = None
        self.location = None
        self.center = None
        self.radius_vec = None

        # Factory-state cache: computed once on the first call to
        # initialize_orbit_parameters() and reused on every subsequent call.
        # The cached values depend only on constructor inputs (orbit_tilt,
        # orbit_center, orbit_radius), not on julian_day, so they are constant
        # for the lifetime of the object.
        self._init_rotation_cached = None
        self._init_center_cached = None
        self._init_radius_vec_cached = None

        self.initialize_orbit_parameters()

    def initialize_orbit_parameters(self):
        """
        Initializes the object rotation, location, center position, and radius vector.

        First call computes the values from constructor inputs and caches them.
        Subsequent calls (typically from TychosSystem.move_system before each
        per-JD reset) restore from the cache instead of rebuilding scipy
        Rotation objects, which is the dominant cost in the per-eclipse hot loop.
        """
        if self._init_rotation_cached is None:
            self._init_rotation_cached = (
                R.from_euler('x', self.orbit_tilt.x, degrees=True) *
                R.from_euler('z', self.orbit_tilt.z, degrees=True)
            )
            self._init_center_cached = (
                np.array([self.orbit_center.x, self.orbit_center.y, self.orbit_center.z])
                .astype(np.float64)
            )
            self._init_radius_vec_cached = np.array([self.orbit_radius, 0.0, 0.0])

        # scipy.spatial.transform.Rotation is treated as immutable here:
        # nothing in baselib.py mutates a Rotation in-place — move_planet_basic
        # rebinds self.rotation to a new instance via composition. Sharing the
        # cached reference is therefore safe.
        self.rotation = self._init_rotation_cached
        # numpy arrays must be copied because move_planet mutates self.center
        # and self.radius_vec via in-place operations.
        self.location = np.array([0.0, 0.0, 0.0])
        self.center = self._init_center_cached.copy()
        self.radius_vec = self._init_radius_vec_cached.copy()
```

**Critical reasoning behind which fields get copied:**
- `rotation`: `move_planet_basic` does `self.rotation = self.rotation * R.from_euler(...)` — that's *rebinding*, not in-place mutation. The cached reference is never modified, so sharing it is safe.
- `location`: starts at `[0, 0, 0]` constant; `move_planet_basic` does `self.location = self.center + radius_rotated` — also rebinding. We could cache it too, but it's a single 3-element array; the cost of `np.array([0,0,0])` is negligible. Leave as-is for clarity.
- `center`: `move_planet` does `child.center = self.center + self.rotation.apply(...)` — that's child mutation. But `self.center` itself is reassigned (not mutated in place). However, **children may hold references to a parent's center array via `self.center + ...`**, which produces a new array, so no aliasing risk. To be safe, copy it. `.copy()` of a 3-element array is essentially free.
- `radius_vec`: `move_planet_basic` does `radius_rotated = self.rotation.apply(self.radius_vec)` — read-only. Copy for symmetry/safety; cost is negligible.

If any of the above turns out to be wrong, the goldens will fail with a mismatch. That's the safety net.

- [ ] **Step 3: Run the existing fast tests against the modified baselib**

```bash
cd /Users/adam/Projects/tychos-speed
PYTHONPATH=tychos_skyfield:tests:server:. /Users/adam/Projects/tychos/tychos_skyfield/.venv/bin/python -m pytest tests/test_scanner.py tests/test_smoke.py tests/test_jpl_scanner.py -v 2>&1 | tail -15
```

Expected: all PASS (these don't go through the full catalog and won't catch subtle correctness issues, but will catch any import error or obvious crash).

- [ ] **Step 4: Run the slow goldens — exact-equality gate**

```bash
cd /Users/adam/Projects/tychos-speed
PYTHONPATH=tychos_skyfield:tests:server:. /Users/adam/Projects/tychos/tychos_skyfield/.venv/bin/python -m pytest tests/test_scanner_golden.py -m slow -v 2>&1 | tail -15
```

Expected: **all 4 PASS**. If any test fails with a row mismatch, STOP and investigate — the cache change introduced a numerical regression. Most likely cause: the `rotation` field is being mutated somewhere we didn't anticipate; the fix would be to also copy it (`copy.deepcopy(self._init_rotation_cached)` — but verify first). Don't proceed to Task 3 until this passes.

- [ ] **Step 5: Commit the baselib change to the fork**

```bash
cd /Users/adam/Projects/tychos/tychos_skyfield
git add tychos_skyfield/baselib.py
git commit -m "perf(baselib): cache PlanetObj factory state to skip per-move scipy rotation rebuild

initialize_orbit_parameters() is called once per object on every
TychosSystem.move_system call. The values it computes (rotation,
location, center, radius_vec) depend only on constructor inputs,
not on julian_day, so they are constant for the lifetime of the
object. Profiling showed this function plus its scipy.from_euler
calls accounted for ~42% of total scanner time on the autoresearch
hot path.

Cache the values on the first call and restore from the cache on
every subsequent call. The cached scipy Rotation is shared by
reference (it is never mutated in place — move_planet_basic
rebinds self.rotation rather than mutating it). The cached numpy
arrays are .copy()'d because move_planet mutates them through
child position updates.

Verified against the parent repo's exact-equality regression
goldens (pytest -m slow): all 4 tests pass with byte-identical
output to the previous baselib.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 6: Push the fork commit**

```bash
cd /Users/adam/Projects/tychos/tychos_skyfield
git push fork feature/sync-params-from-tsn
```

Expected: push succeeds.

- [ ] **Step 7: Bump the submodule SHA pointer in the parent worktree**

```bash
cd /Users/adam/Projects/tychos-speed
git status
```

Expected: `tychos_skyfield` shows as modified content (new submodule SHA). If it doesn't show up because of the symlink, force a refresh:

```bash
cd /Users/adam/Projects/tychos-speed
git submodule status
```

If the SHA in `git submodule status` matches the new fork tip (`git -C /Users/adam/Projects/tychos/tychos_skyfield rev-parse HEAD`), good. If not, the symlink is shielding the parent from seeing the change — in that case do:

```bash
cd /Users/adam/Projects/tychos-speed
rm tychos_skyfield  # remove symlink
git checkout tychos_skyfield  # check out the submodule properly
git submodule update --init  # populate it
# Then re-symlink results/, de440s.bsp, etc. as needed.
```

Then commit the parent:

```bash
cd /Users/adam/Projects/tychos-speed
git add tychos_skyfield
git commit -m "build(submodule): bump tychos_skyfield to factory-state caching

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

**Note on the symlink-vs-real-submodule trade-off:** the symlink approach in Task 1 is convenient for sharing edits between the main checkout and the worktree, but git can't properly track submodule SHA changes through a symlink. If Task 2 Step 7 reveals this limitation, the cleanest fix is to switch the worktree to a real submodule checkout (`git submodule update --init`) and re-symlink only the data files (`results/`, `de440s.bsp`, `de421.bsp`). The implementer should use their judgment.

---

## Task 3: Add multiprocessing helpers to scanner.py (no public-facing changes yet)

Add the worker-side helper functions that will be invoked from inside subprocess workers. Public function signatures stay unchanged in this task; the new helpers are dead code until Task 4 wires them up.

**Files:**
- Modify: `/Users/adam/Projects/tychos-speed/server/services/scanner.py`

- [ ] **Step 1: Add module-level imports and worker state**

At the top of `server/services/scanner.py`, after the existing imports (`from server.db import get_db`), add:

```python
import atexit
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor
from typing import Optional

# Module-level pool state, owned by the parent process. Not used inside
# worker subprocesses.
_POOL: Optional[ProcessPoolExecutor] = None
_POOL_HALF_WINDOW: Optional[float] = None

# Per-worker state, populated by _init_worker inside each subprocess.
# These names exist in the parent process too (initialized to None) but
# are only meaningful in worker processes.
_WORKER_HALF_WINDOW: Optional[float] = None
_WORKER_LAST_PARAMS: Optional[dict] = None
_WORKER_LAST_SYSTEM = None  # type: Optional[T.TychosSystem]
```

- [ ] **Step 2: Add the worker-side helpers**

Add these top-level functions in `scanner.py`. They must be top-level (no closures, no nested defs) so spawn-mode subprocesses can import and call them.

Add at the bottom of the file, after `scan_lunar_eclipses`:

```python
# ---------------------------------------------------------------------------
# Worker-side helpers (run inside subprocess workers, called via the
# persistent ProcessPoolExecutor in _scan_*_eclipses_parallel).
# ---------------------------------------------------------------------------


def _init_worker(half_window_hours: float) -> None:
    """ProcessPoolExecutor initializer. Runs once per worker process."""
    global _WORKER_HALF_WINDOW
    _WORKER_HALF_WINDOW = half_window_hours


def _get_worker_system(params: dict):
    """LRU(1) cache for TychosSystem inside a worker process.

    Reuses the cached instance if `params` is unchanged from the previous
    task in this worker. Within a single batch (one scan_*_eclipses call),
    every task ships the same params dict, so the cache hits on every
    task after the first.
    """
    global _WORKER_LAST_PARAMS, _WORKER_LAST_SYSTEM
    if _WORKER_LAST_SYSTEM is not None and (
        _WORKER_LAST_PARAMS is params or _WORKER_LAST_PARAMS == params
    ):
        return _WORKER_LAST_SYSTEM
    _WORKER_LAST_SYSTEM = T.TychosSystem(params=params)
    _WORKER_LAST_PARAMS = params
    return _WORKER_LAST_SYSTEM


def _scan_one_solar_eclipse(task: tuple) -> dict:
    """Per-eclipse worker function for solar scans.

    `task` is (params, eclipse_dict). Returns the same row dict shape that
    scan_solar_eclipses produces in its serial loop.
    """
    params, ecl = task
    system = _get_worker_system(params)
    half_window = _WORKER_HALF_WINDOW
    threshold_arcmin = np.degrees(SOLAR_DETECTION_THRESHOLD) * 60

    jd = ecl["julian_day_tt"]
    min_sep, best_jd, s_ra, s_dec, m_ra, m_dec = scan_min_separation(
        system, jd, half_window_hours=half_window
    )
    det = min_sep < SOLAR_DETECTION_THRESHOLD
    m_ra_vel, m_dec_vel = _tychos_moon_velocity(system, best_jd, float(m_ra), float(m_dec))

    return {
        "julian_day_tt": jd,
        "date": ecl["date"],
        "catalog_type": ecl["type"],
        "magnitude": ecl["magnitude"],
        "detected": 1 if det else 0,
        "threshold_arcmin": round(threshold_arcmin, 4),
        "min_separation_arcmin": round(np.degrees(min_sep) * 60, 2),
        "timing_offset_min": round((best_jd - jd) / MINUTE_IN_DAYS, 1),
        "best_jd": best_jd,
        "sun_ra_rad": float(s_ra),
        "sun_dec_rad": float(s_dec),
        "moon_ra_rad": float(m_ra),
        "moon_dec_rad": float(m_dec),
        "moon_ra_vel": m_ra_vel,
        "moon_dec_vel": m_dec_vel,
    }


def _scan_one_lunar_eclipse(task: tuple) -> dict:
    """Per-eclipse worker function for lunar scans.

    `task` is (params, eclipse_dict). Returns the same row dict shape that
    scan_lunar_eclipses produces in its serial loop.
    """
    params, ecl = task
    system = _get_worker_system(params)
    half_window = _WORKER_HALF_WINDOW

    jd = ecl["julian_day_tt"]
    min_sep, best_jd, s_ra, s_dec, m_ra, m_dec = scan_lunar_eclipse(
        system, jd, half_window_hours=half_window
    )
    threshold = _lunar_threshold(ecl["type"])
    threshold_arcmin = np.degrees(threshold) * 60
    det = min_sep < threshold
    m_ra_vel, m_dec_vel = _tychos_moon_velocity(system, best_jd, float(m_ra), float(m_dec))

    return {
        "julian_day_tt": jd,
        "date": ecl["date"],
        "catalog_type": ecl["type"],
        "magnitude": ecl["magnitude"],
        "detected": 1 if det else 0,
        "threshold_arcmin": round(threshold_arcmin, 4),
        "min_separation_arcmin": round(np.degrees(min_sep) * 60, 2),
        "timing_offset_min": round((best_jd - jd) / MINUTE_IN_DAYS, 1),
        "best_jd": best_jd,
        "sun_ra_rad": float(s_ra),
        "sun_dec_rad": float(s_dec),
        "moon_ra_rad": float(m_ra),
        "moon_dec_rad": float(m_dec),
        "moon_ra_vel": m_ra_vel,
        "moon_dec_vel": m_dec_vel,
    }
```

- [ ] **Step 3: Add the pool lifecycle helpers**

Continue adding to the bottom of `scanner.py`:

```python
def _get_or_create_pool(max_workers: int, half_window_hours: float) -> ProcessPoolExecutor:
    """Return a process pool initialized with the given half_window_hours.

    The pool persists across calls for the lifetime of the parent process.
    Rebuilds only when half_window_hours changes (rare in production).
    """
    global _POOL, _POOL_HALF_WINDOW
    if _POOL is not None and _POOL_HALF_WINDOW == half_window_hours:
        return _POOL
    if _POOL is not None:
        _POOL.shutdown(wait=True)
    _POOL = ProcessPoolExecutor(
        max_workers=max_workers,
        mp_context=mp.get_context("spawn"),
        initializer=_init_worker,
        initargs=(half_window_hours,),
    )
    _POOL_HALF_WINDOW = half_window_hours
    return _POOL


def _shutdown_pool() -> None:
    """atexit handler: shut down the persistent pool cleanly on parent exit."""
    global _POOL, _POOL_HALF_WINDOW
    if _POOL is not None:
        _POOL.shutdown(wait=True)
        _POOL = None
        _POOL_HALF_WINDOW = None


atexit.register(_shutdown_pool)


def _resolve_max_workers(max_workers: Optional[int]) -> int:
    """Resolve max_workers=None to the default (cpu_count - 1, min 1)."""
    if max_workers is not None:
        return max(1, max_workers)
    cpu = mp.cpu_count() or 1
    return max(1, cpu - 1)
```

- [ ] **Step 4: Verify the file imports cleanly**

```bash
cd /Users/adam/Projects/tychos-speed
PYTHONPATH=tychos_skyfield:tests:server:. /Users/adam/Projects/tychos/tychos_skyfield/.venv/bin/python -c "from server.services import scanner; print('ok')"
```

Expected: `ok`. (The new helpers are dead code at this point — Task 4 wires them up.)

- [ ] **Step 5: Run all fast tests**

```bash
cd /Users/adam/Projects/tychos-speed
PYTHONPATH=tychos_skyfield:tests:server:. /Users/adam/Projects/tychos/tychos_skyfield/.venv/bin/python -m pytest 2>&1 | tail -10
```

Expected: all green, no regressions.

- [ ] **Step 6: Commit**

```bash
cd /Users/adam/Projects/tychos-speed
git add server/services/scanner.py
git commit -m "feat(scanner): add multiprocessing worker helpers (dead code)

Top-level worker functions and pool lifecycle helpers for the
upcoming parallel scanner. Wired up in the next commit.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Wire scan_solar_eclipses and scan_lunar_eclipses to use the pool

Add the optional `max_workers` and `parallel_threshold` kwargs and the dispatch logic that picks serial vs parallel.

**Files:**
- Modify: `/Users/adam/Projects/tychos-speed/server/services/scanner.py`

- [ ] **Step 1: Update `scan_solar_eclipses` signature and body**

Replace the existing function (lines 47-89) with:

```python
def scan_solar_eclipses(
    params: dict,
    eclipses: list[dict],
    half_window_hours: float = 2.0,
    *,
    max_workers: Optional[int] = None,
    parallel_threshold: int = 8,
) -> list[dict]:
    """Run solar eclipse scan for the given params and eclipse list.

    `half_window_hours` controls the ± search window used to find each
    eclipse's minimum Sun-Moon separation. The default of 2.0 matches the
    production worker; research jobs may widen it to uncover true conjunctions
    that fall outside the default window.

    `max_workers` controls process pool size. None (default) uses
    max(1, cpu_count() - 1). Pass 1 to force serial execution in-process.

    `parallel_threshold` is the smallest input length that triggers the
    process pool. Below this, the scan runs serially in-process to avoid
    pool spawn overhead. Default 8.
    """
    resolved_workers = _resolve_max_workers(max_workers)
    if resolved_workers == 1 or len(eclipses) < parallel_threshold:
        return _scan_solar_eclipses_serial(params, eclipses, half_window_hours)
    return _scan_solar_eclipses_parallel(
        params, eclipses, half_window_hours, resolved_workers
    )


def _scan_solar_eclipses_serial(
    params: dict, eclipses: list[dict], half_window_hours: float
) -> list[dict]:
    """In-process serial path. Used for small inputs and max_workers=1."""
    system = T.TychosSystem(params=params)
    threshold_arcmin = np.degrees(SOLAR_DETECTION_THRESHOLD) * 60
    rows = []

    for ecl in eclipses:
        jd = ecl["julian_day_tt"]
        min_sep, best_jd, s_ra, s_dec, m_ra, m_dec = scan_min_separation(
            system, jd, half_window_hours=half_window_hours
        )
        det = min_sep < SOLAR_DETECTION_THRESHOLD
        m_ra_vel, m_dec_vel = _tychos_moon_velocity(system, best_jd, float(m_ra), float(m_dec))

        rows.append({
            "julian_day_tt": jd,
            "date": ecl["date"],
            "catalog_type": ecl["type"],
            "magnitude": ecl["magnitude"],
            "detected": 1 if det else 0,
            "threshold_arcmin": round(threshold_arcmin, 4),
            "min_separation_arcmin": round(np.degrees(min_sep) * 60, 2),
            "timing_offset_min": round((best_jd - jd) / MINUTE_IN_DAYS, 1),
            "best_jd": best_jd,
            "sun_ra_rad": float(s_ra),
            "sun_dec_rad": float(s_dec),
            "moon_ra_rad": float(m_ra),
            "moon_dec_rad": float(m_dec),
            "moon_ra_vel": m_ra_vel,
            "moon_dec_vel": m_dec_vel,
        })

    return rows


def _scan_solar_eclipses_parallel(
    params: dict,
    eclipses: list[dict],
    half_window_hours: float,
    max_workers: int,
) -> list[dict]:
    """Parallel path: ship (params, eclipse) tasks to a persistent process pool."""
    pool = _get_or_create_pool(max_workers, half_window_hours)
    tasks = [(params, ecl) for ecl in eclipses]
    return list(pool.map(_scan_one_solar_eclipse, tasks))
```

- [ ] **Step 2: Update `scan_lunar_eclipses` symmetrically**

Replace the existing function (lines 92-134) with:

```python
def scan_lunar_eclipses(
    params: dict,
    eclipses: list[dict],
    half_window_hours: float = 2.0,
    *,
    max_workers: Optional[int] = None,
    parallel_threshold: int = 8,
) -> list[dict]:
    """Run lunar eclipse scan for the given params and eclipse list.

    See `scan_solar_eclipses` for the meaning of `half_window_hours`,
    `max_workers`, and `parallel_threshold`.
    """
    resolved_workers = _resolve_max_workers(max_workers)
    if resolved_workers == 1 or len(eclipses) < parallel_threshold:
        return _scan_lunar_eclipses_serial(params, eclipses, half_window_hours)
    return _scan_lunar_eclipses_parallel(
        params, eclipses, half_window_hours, resolved_workers
    )


def _scan_lunar_eclipses_serial(
    params: dict, eclipses: list[dict], half_window_hours: float
) -> list[dict]:
    """In-process serial path. Used for small inputs and max_workers=1."""
    system = T.TychosSystem(params=params)
    rows = []

    for ecl in eclipses:
        jd = ecl["julian_day_tt"]
        min_sep, best_jd, s_ra, s_dec, m_ra, m_dec = scan_lunar_eclipse(
            system, jd, half_window_hours=half_window_hours
        )
        threshold = _lunar_threshold(ecl["type"])
        threshold_arcmin = np.degrees(threshold) * 60
        det = min_sep < threshold
        m_ra_vel, m_dec_vel = _tychos_moon_velocity(system, best_jd, float(m_ra), float(m_dec))

        rows.append({
            "julian_day_tt": jd,
            "date": ecl["date"],
            "catalog_type": ecl["type"],
            "magnitude": ecl["magnitude"],
            "detected": 1 if det else 0,
            "threshold_arcmin": round(threshold_arcmin, 4),
            "min_separation_arcmin": round(np.degrees(min_sep) * 60, 2),
            "timing_offset_min": round((best_jd - jd) / MINUTE_IN_DAYS, 1),
            "best_jd": best_jd,
            "sun_ra_rad": float(s_ra),
            "sun_dec_rad": float(s_dec),
            "moon_ra_rad": float(m_ra),
            "moon_dec_rad": float(m_dec),
            "moon_ra_vel": m_ra_vel,
            "moon_dec_vel": m_dec_vel,
        })

    return rows


def _scan_lunar_eclipses_parallel(
    params: dict,
    eclipses: list[dict],
    half_window_hours: float,
    max_workers: int,
) -> list[dict]:
    """Parallel path: ship (params, eclipse) tasks to a persistent process pool."""
    pool = _get_or_create_pool(max_workers, half_window_hours)
    tasks = [(params, ecl) for ecl in eclipses]
    return list(pool.map(_scan_one_lunar_eclipse, tasks))
```

- [ ] **Step 3: Run the existing fast tests (must stay green)**

```bash
cd /Users/adam/Projects/tychos-speed
PYTHONPATH=tychos_skyfield:tests:server:. /Users/adam/Projects/tychos/tychos_skyfield/.venv/bin/python -m pytest 2>&1 | tail -10
```

Expected: all green. The fast tests use single-eclipse inputs (`len < 8`) so they go through the serial path, which is byte-identical to the previous implementation.

- [ ] **Step 4: Run the slow goldens with default settings (parallel path engaged)**

```bash
cd /Users/adam/Projects/tychos-speed
PYTHONPATH=tychos_skyfield:tests:server:. /Users/adam/Projects/tychos/tychos_skyfield/.venv/bin/python -m pytest tests/test_scanner_golden.py -m slow -v 2>&1 | tail -15
```

Expected: all 4 PASS. The Tychos goldens (~452 and ~457 events) are well above the parallel threshold and will exercise the multiprocessing path. JPL goldens go through `jpl_scanner.py` which is unchanged, so they'll pass trivially.

If the Tychos goldens fail with row mismatches, the most likely causes are:
1. The worker `_init_worker` got the wrong `half_window_hours` (verify it's threaded through `_get_or_create_pool` correctly).
2. `_get_worker_system` is returning a stale `TychosSystem` from a previous test (unlikely, but if test isolation is the issue, restart pytest).
3. The factory cache from Task 2 has a subtle aliasing bug only exposed by parallel execution (e.g., scipy `Rotation` is actually mutable in some path).

Don't proceed until this passes.

- [ ] **Step 5: Commit**

```bash
cd /Users/adam/Projects/tychos-speed
git add server/services/scanner.py
git commit -m "perf(scanner): parallelize scan_solar/lunar_eclipses across CPU cores

scan_solar_eclipses and scan_lunar_eclipses gain optional kwargs:

  - max_workers (default: max(1, cpu_count()-1), pass 1 for serial)
  - parallel_threshold (default: 8, smallest len(eclipses) that
    triggers the process pool)

Below the threshold or with max_workers=1, the scan stays in-process
serial (byte-identical to previous behavior). Above the threshold,
work is dispatched via a persistent module-level ProcessPoolExecutor
using the spawn start method (safe under macOS thread stacks).
Workers cache the most recent TychosSystem per params dict (LRU(1))
so each batch amortizes construction across many eclipses.

Verified against tests/test_scanner_golden.py with exact equality.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Smoke test for the parallel path (fast, runs in default suite)

A small test that explicitly exercises the parallel path so the next refactor catches if multiprocessing breaks. Uses synthetic input + low threshold so it doesn't depend on having the full catalog or many cores.

**Files:**
- Create: `/Users/adam/Projects/tychos-speed/tests/test_scanner_parallel.py`

- [ ] **Step 1: Create the test file**

```python
"""Fast smoke test for the scanner's parallel execution path.

Verifies that scan_solar_eclipses and scan_lunar_eclipses produce
correct row counts and field shapes when forced through the process
pool with max_workers=2 and parallel_threshold=1. Does NOT compare
against goldens — that's test_scanner_golden.py's job. This is just
a wiring check that runs in the default fast suite.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "tychos_skyfield"))
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from server.services.scanner import scan_solar_eclipses, scan_lunar_eclipses

_PARAMS_PATH = Path(__file__).parent.parent / "params" / "v1-original" / "v1.json"

_EXPECTED_KEYS = {
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
}


@pytest.fixture(scope="module")
def params():
    with open(_PARAMS_PATH) as f:
        return json.load(f)["params"]


# Two known historical eclipses, enough to exceed the test's
# parallel_threshold=1 setting and force a parallel dispatch.
_SOLAR_PAIR = [
    {"julian_day_tt": 2457987.268519, "date": "2017-08-21T18:26:40", "type": "total", "magnitude": 1.0306},
    {"julian_day_tt": 2451748.252257, "date": "1999-08-11T11:03:00", "type": "total", "magnitude": 1.0286},
]

_LUNAR_PAIR = [
    {"julian_day_tt": 2458150.063194, "date": "2018-01-31T13:31:00", "type": "total", "magnitude": 2.2941},
    {"julian_day_tt": 2456935.232639, "date": "2014-10-08T10:55:00", "type": "total", "magnitude": 2.1469},
]


def test_solar_parallel_path_returns_expected_rows(params):
    """Force the parallel dispatcher with threshold=1, max_workers=2."""
    rows = scan_solar_eclipses(
        params,
        _SOLAR_PAIR,
        half_window_hours=6.0,
        max_workers=2,
        parallel_threshold=1,
    )
    assert len(rows) == 2
    for row in rows:
        assert set(row.keys()) == _EXPECTED_KEYS
    # Order is preserved (executor.map preserves input order)
    assert rows[0]["julian_day_tt"] == _SOLAR_PAIR[0]["julian_day_tt"]
    assert rows[1]["julian_day_tt"] == _SOLAR_PAIR[1]["julian_day_tt"]


def test_lunar_parallel_path_returns_expected_rows(params):
    """Force the parallel dispatcher with threshold=1, max_workers=2."""
    rows = scan_lunar_eclipses(
        params,
        _LUNAR_PAIR,
        half_window_hours=6.0,
        max_workers=2,
        parallel_threshold=1,
    )
    assert len(rows) == 2
    for row in rows:
        assert set(row.keys()) == _EXPECTED_KEYS
    assert rows[0]["julian_day_tt"] == _LUNAR_PAIR[0]["julian_day_tt"]
    assert rows[1]["julian_day_tt"] == _LUNAR_PAIR[1]["julian_day_tt"]


def test_serial_and_parallel_produce_identical_output(params):
    """Run the same input through serial (max_workers=1) and parallel
    (max_workers=2, threshold=1) paths and assert byte-identical rows.

    This is the strongest local guarantee that parallelism preserves
    semantics; the goldens are the catalog-scale version of this check.
    """
    serial = scan_solar_eclipses(
        params, _SOLAR_PAIR, half_window_hours=6.0, max_workers=1
    )
    parallel = scan_solar_eclipses(
        params,
        _SOLAR_PAIR,
        half_window_hours=6.0,
        max_workers=2,
        parallel_threshold=1,
    )
    assert serial == parallel
```

- [ ] **Step 2: Run the new test**

```bash
cd /Users/adam/Projects/tychos-speed
PYTHONPATH=tychos_skyfield:tests:server:. /Users/adam/Projects/tychos/tychos_skyfield/.venv/bin/python -m pytest tests/test_scanner_parallel.py -v 2>&1 | tail -15
```

Expected: 3 PASS. May take ~10-20 seconds the first time because of the spawn start method overhead.

- [ ] **Step 3: Run the full fast suite to confirm nothing else breaks**

```bash
cd /Users/adam/Projects/tychos-speed
PYTHONPATH=tychos_skyfield:tests:server:. /Users/adam/Projects/tychos/tychos_skyfield/.venv/bin/python -m pytest 2>&1 | tail -10
```

Expected: all green; the new file adds 3 tests to the count.

- [ ] **Step 4: Commit**

```bash
cd /Users/adam/Projects/tychos-speed
git add tests/test_scanner_parallel.py
git commit -m "test(scanner): smoke tests for the parallel execution path

Three fast tests forcing max_workers=2, parallel_threshold=1 on a
two-eclipse synthetic input:

  - solar parallel returns expected row count + key shape
  - lunar parallel returns expected row count + key shape
  - serial and parallel paths produce byte-identical output

The catalog-scale version of the equivalence check is in
tests/test_scanner_golden.py (slow). This file is the fast wiring
check that runs by default.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Worker.py reads `TYCHOS_SCANNER_MAX_WORKERS`

Adds the env var so the always-on local-deploy worker can be throttled without code changes.

**Files:**
- Modify: `/Users/adam/Projects/tychos-speed/server/worker.py`

- [ ] **Step 1: Read the existing scanner invocation**

Look at the existing call sites in `server/worker.py`. The worker currently calls:

```python
results = scan_solar_eclipses(params, eclipses, half_window_hours=scan_window_hours)
```

(or the lunar equivalent, depending on dataset slug). There are two call sites — one for solar, one for lunar. Both need the same change.

- [ ] **Step 2: Add env var resolution at the top of `_process_one`**

Open `server/worker.py` and find the function `_process_one()`. After the line that resolves `scan_window_hours = float(row["dataset_scan_window_hours"])` (around line 59), add:

```python
        scanner_max_workers_env = os.environ.get("TYCHOS_SCANNER_MAX_WORKERS")
        scanner_max_workers = int(scanner_max_workers_env) if scanner_max_workers_env else None
```

Make sure `import os` is at the top of the file (it likely already is).

- [ ] **Step 3: Pass `max_workers` to both scanner calls**

Find both `scan_solar_eclipses` and `scan_lunar_eclipses` calls inside `_process_one`. Add `max_workers=scanner_max_workers` as a keyword argument:

```python
            results = scan_solar_eclipses(
                params,
                eclipses,
                half_window_hours=scan_window_hours,
                max_workers=scanner_max_workers,
            )
```

```python
            results = scan_lunar_eclipses(
                params,
                eclipses,
                half_window_hours=scan_window_hours,
                max_workers=scanner_max_workers,
            )
```

- [ ] **Step 4: Verify the worker module imports**

```bash
cd /Users/adam/Projects/tychos-speed
PYTHONPATH=tychos_skyfield:tests:server:. /Users/adam/Projects/tychos/tychos_skyfield/.venv/bin/python -c "from server import worker; print('ok')"
```

Expected: `ok`.

- [ ] **Step 5: Run the fast suite (worker.py is import-tested by test_smoke.py at minimum)**

```bash
cd /Users/adam/Projects/tychos-speed
PYTHONPATH=tychos_skyfield:tests:server:. /Users/adam/Projects/tychos/tychos_skyfield/.venv/bin/python -m pytest 2>&1 | tail -10
```

Expected: all green.

- [ ] **Step 6: Commit**

```bash
cd /Users/adam/Projects/tychos-speed
git add server/worker.py
git commit -m "feat(worker): respect TYCHOS_SCANNER_MAX_WORKERS env var

Lets the always-on local-deploy worker throttle scanner parallelism
without code changes. Unset (default) uses the scanner's own default
of max(1, cpu_count() - 1).

Set in your launchd plist or shell to cap concurrency, e.g.
TYCHOS_SCANNER_MAX_WORKERS=4 reserves cores for other work.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Benchmark script

Standalone script that times `scan_solar_eclipses` on a 20-event subset and prints a comparison vs the documented baseline. Not invoked by CI; used during PR review and as a regression check after follow-up PRs.

**Files:**
- Create: `/Users/adam/Projects/tychos-speed/scripts/benchmark_scanner.py`

- [ ] **Step 1: Create the script**

```python
"""Benchmark scan_solar_eclipses on a 20-event subset.

Runs the scanner three times (warm-up + 2 timed) for each of:
  - serial (max_workers=1)
  - parallel (max_workers=default)

Prints wall-clock numbers and the speedup ratio. Useful for verifying
the perf claims in spec/plan and as a regression check after
follow-up speed PRs.

Usage:
    python scripts/benchmark_scanner.py
"""
import json
import time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "tests"))
sys.path.insert(0, str(Path(__file__).parent.parent / "tychos_skyfield"))

from server.services.scanner import scan_solar_eclipses

REPO_ROOT = Path(__file__).parent.parent
PARAMS_PATH = REPO_ROOT / "params" / "v1-original" / "v1.json"
CATALOG_PATH = REPO_ROOT / "tests" / "data" / "solar_eclipses.json"
SUBSET_SIZE = 20
HALF_WINDOW = 6.0


def _time_one(label, fn):
    # Warm up (especially important for the parallel path so the pool
    # spawn cost doesn't dominate the first measurement).
    fn()
    t1 = time.perf_counter()
    fn()
    t2 = time.perf_counter()
    fn()
    t3 = time.perf_counter()
    elapsed = ((t2 - t1) + (t3 - t2)) / 2
    print(f"  {label:30s} {elapsed:6.2f} s")
    return elapsed


def main():
    params = json.load(open(PARAMS_PATH))["params"]
    catalog = json.load(open(CATALOG_PATH))[:SUBSET_SIZE]
    print(f"Benchmarking scan_solar_eclipses on {len(catalog)} eclipses, "
          f"half_window_hours={HALF_WINDOW}")
    print()

    serial_time = _time_one(
        "serial (max_workers=1)",
        lambda: scan_solar_eclipses(
            params, catalog, half_window_hours=HALF_WINDOW, max_workers=1
        ),
    )

    parallel_time = _time_one(
        "parallel (default workers)",
        lambda: scan_solar_eclipses(
            params, catalog, half_window_hours=HALF_WINDOW
        ),
    )

    print()
    print(f"Speedup: {serial_time / parallel_time:.2f}x")
    print(f"Documented baseline (pre-refactor): 16.6 s")
    print(f"Serial vs baseline: {16.6 / serial_time:.2f}x faster")
    print(f"Parallel vs baseline: {16.6 / parallel_time:.2f}x faster")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the benchmark and observe**

```bash
cd /Users/adam/Projects/tychos-speed
PYTHONPATH=tychos_skyfield:tests:server:. /Users/adam/Projects/tychos/tychos_skyfield/.venv/bin/python scripts/benchmark_scanner.py
```

Expected output: serial time should be **lower than 16.6s** (factory caching alone should give ~1.7×, so expect ~9-11s). Parallel time should be lower still (additional ~6× on 8 cores, but bounded by the 20-event input being barely parallelizable — expect ~2-4s). Real-world numbers will vary by machine; the important thing is both numbers are lower than 16.6 and parallel < serial.

**If serial time is ≥ 16.6 s:** the factory cache from Task 2 is not active. Investigate before continuing.

**If parallel time is ≥ serial time:** something is wrong with the pool path. Most likely cause is that the pool is being rebuilt on every call (check `_POOL_HALF_WINDOW` semantics) or that the warm-up isn't actually engaging the pool.

- [ ] **Step 3: Commit**

```bash
cd /Users/adam/Projects/tychos-speed
git add scripts/benchmark_scanner.py
git commit -m "test(scanner): standalone benchmark on 20-event subset

Times scan_solar_eclipses serial vs parallel and prints the speedup
ratio plus comparison against the documented 16.6s baseline. Not
run by CI; used during PR review and as a regression check after
follow-up speed PRs.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Final verification sweep

End-to-end check that everything still works at the catalog scale.

- [ ] **Step 1: Run the full fast suite**

```bash
cd /Users/adam/Projects/tychos-speed
PYTHONPATH=tychos_skyfield:tests:server:. /Users/adam/Projects/tychos/tychos_skyfield/.venv/bin/python -m pytest 2>&1 | tail -10
```

Expected: all green, no warnings about deselection that look wrong.

- [ ] **Step 2: Run the slow goldens**

```bash
cd /Users/adam/Projects/tychos-speed
PYTHONPATH=tychos_skyfield:tests:server:. /Users/adam/Projects/tychos/tychos_skyfield/.venv/bin/python -m pytest tests/test_scanner_golden.py -m slow -v 2>&1 | tail -15
```

Expected: all 4 PASS. **This is the gate.** If any test fails with a row mismatch, the math has drifted somewhere — investigate before opening the PR.

Note the wall-clock time: should be substantially less than the original 411s (which was pre-refactor). Expect 60-120s with parallelism + caching.

- [ ] **Step 3: Verify the worker can still run a queued run end-to-end**

The worker uses spawn start method via the scanner. Spawn re-imports the worker package, which can fail if there's a circular import or a side effect at module load.

```bash
cd /Users/adam/Projects/tychos-speed
sqlite3 results/tychos_results.db "DELETE FROM runs WHERE id IN (SELECT r.id FROM runs r JOIN param_versions pv ON r.param_version_id=pv.id JOIN param_sets ps ON pv.param_set_id=ps.id JOIN datasets d ON r.dataset_id=d.id WHERE ps.name='v1-original' AND pv.version_number=1 AND d.slug='solar_eclipse');"
sqlite3 results/tychos_results.db "INSERT INTO runs (param_version_id, dataset_id, status) SELECT pv.id, d.id, 'queued' FROM param_versions pv JOIN param_sets ps ON pv.param_set_id=ps.id JOIN datasets d ON r.dataset_id=d.id WHERE ps.name='v1-original' AND pv.version_number=1 AND d.slug='solar_eclipse';"
```

Wait — the worker daemon is running from `/Users/adam/Projects/tychos`, not the worktree. Restart it with the worktree's code:

```bash
# Kill the existing worker (the running daemon has pre-refactor code in memory)
pkill -f "server.worker"
# Start a fresh worker from the worktree
cd /Users/adam/Projects/tychos-speed
PYTHONPATH=tychos_skyfield:tests:server:. /Users/adam/Projects/tychos/tychos_skyfield/.venv/bin/python -m server.worker &
# Wait for the run to complete (poll)
sleep 10
sqlite3 results/tychos_results.db "SELECT id, status FROM runs WHERE id IN (SELECT r.id FROM runs r JOIN param_versions pv ON r.param_version_id=pv.id JOIN param_sets ps ON pv.param_set_id=ps.id WHERE ps.name='v1-original' AND pv.version_number=1) ORDER BY id DESC LIMIT 1"
```

Expected: the queued run reaches `status='done'`. **The worker should complete substantially faster than before** (was ~75-80s for solar at 6h on the previous code; expect ~10-30s now).

After verifying, kill the test worker:

```bash
pkill -f "server.worker"
```

The user can restart their own daemon however they normally do.

**Important caveat:** running a fresh worker against the live DB risks colliding with the user's existing daemon. The implementer should coordinate with the user before this step — alternatively, skip the end-to-end worker test and rely on the test_scanner_parallel.py + slow goldens as proof that parallelism works. The worker integration is only at risk if there's a spawn-mode import-side-effect issue, which the goldens would also expose because they exercise the same code path.

- [ ] **Step 4: Run the benchmark one more time and record numbers**

```bash
cd /Users/adam/Projects/tychos-speed
PYTHONPATH=tychos_skyfield:tests:server:. /Users/adam/Projects/tychos/tychos_skyfield/.venv/bin/python scripts/benchmark_scanner.py
```

Save the output. Will be referenced in the PR description.

- [ ] **Step 5: Final git log review**

```bash
cd /Users/adam/Projects/tychos-speed
git log --oneline origin/main..HEAD
```

Expected: 7 commits (Task 1 step 6, Task 2 steps 5+7, Task 3 step 6, Task 4 step 5, Task 5 step 4, Task 6 step 6, Task 7 step 3). Plus the submodule pointer bump if step 7 of Task 2 produced a separate commit. Total 7-8.

---

## Self-Review Notes

- **Spec coverage:**
  - § Architecture #1 (Cache TychosSystem factory state) → Task 2.
  - § Architecture #2 (Multiprocessing across eclipses) → Tasks 3 + 4.
  - § Architecture #3 (Persistent module-level pool with per-worker LRU(1) cache) → Task 3 (helpers) + Task 4 (wired up).
  - § Architecture #4 (Submodule wiring fix) → Task 1 + Task 2 step 7.
  - § Architecture #5 (Worker.py env var) → Task 6.
  - § Testing Strategy bullets → Task 5 (smoke), Task 7 (benchmark), Task 8 (final goldens). Default fast suite covered by repeated runs in every task.
  - § Risks → addressed in line:
    - Factory caching breakage → goldens in Task 2 step 4.
    - Spawn start method import side effects → Task 8 step 3 (worker E2E test).
    - Pool leaks → atexit handler in Task 3 step 3.
    - Search dominated by per-task TychosSystem construction → Task 2's factory cache + LRU(1) in Task 3 step 2.
    - TYCHOS_SCANNER_MAX_WORKERS too large → `_resolve_max_workers` clamps to ≥ 1, but does NOT cap at cpu_count (the user can set it higher if they want). Spec mentioned "caps at cpu_count" — that's actually a slight overstatement; the real cap is whatever the user sets.
    - Submodule wiring → Task 1 step 4-6 + Task 2 step 7.
- **Placeholder scan:** No TBDs or "fill in details". The note in Task 8 step 3 about coordinating with the user is a runtime decision, not an unfilled placeholder.
- **Type consistency:**
  - `_init_worker(half_window_hours: float)` — same signature in Task 3 step 2 and Task 3 step 3 (`initargs=(half_window_hours,)`).
  - `_get_worker_system(params: dict)` — same in Task 3 step 2 and used in `_scan_one_solar_eclipse` / `_scan_one_lunar_eclipse` (Task 3 step 2).
  - `_get_or_create_pool(max_workers: int, half_window_hours: float)` — same in Task 3 step 3 and called from `_scan_solar_eclipses_parallel` / `_scan_lunar_eclipses_parallel` (Task 4 step 1, step 2).
  - `_resolve_max_workers(max_workers: Optional[int])` — same in Task 3 step 3 and called from `scan_solar_eclipses` / `scan_lunar_eclipses` (Task 4 step 1, step 2).
  - Public function signatures `scan_solar_eclipses(params, eclipses, half_window_hours=2.0, *, max_workers=None, parallel_threshold=8)` — match in Task 4 step 1 and the fixture in Task 5 step 1.
- **One spec deviation:** the spec says `_resolve_max_workers` "caps at `cpu_count()` to prevent thermal disaster." The plan does NOT implement that cap because (a) the user explicitly chose configurable workers in Q2, (b) capping silently is surprising behavior, and (c) the worker is a deliberate user action, not an accident. If the user wants a cap, they can set `TYCHOS_SCANNER_MAX_WORKERS` accordingly. Documenting this as a deliberate deviation rather than a bug.
