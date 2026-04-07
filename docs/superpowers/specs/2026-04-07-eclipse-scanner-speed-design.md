# Eclipse Scanner Speed Refactor (Round 1)

**Date:** 2026-04-07
**Status:** Design approved, pending implementation plan
**Owner:** Adam
**Related:** Builds on `docs/superpowers/specs/2026-04-07-eclipse-scanner-goldens-design.md` and uses the regression goldens it produced as the safety net.

## Purpose

Make the eclipse scanner significantly faster so the autoresearch loop is usable. The autoresearch search command runs Nelder-Mead optimization that calls the scanner ~50–100 times per search, and the worker.py validate command runs a full ~900-event catalog scan per parameter set. Both currently take minutes per call.

The combined optimizations in this round target a ~10× speedup with **zero changes to scanner math**. Exact-equality regression goldens must continue to pass.

## Non-Goals

- Replacing `scipy.spatial.transform.Rotation` with hand-rolled numpy rotation matrices. That's a separate ~2-3× win but introduces bit-level numerical risk that could change goldens; it gets its own PR.
- Vectorizing `move_system` to accept JD arrays. Biggest possible win but largest refactor; out of scope.
- Parallel multistart Nelder-Mead in `server/research/search.py`. Different algorithm with different convergence semantics; out of scope.
- Changing the autoresearch CLI surface or `run_search` signature.

## Profiling Evidence

A cProfile run of `scan_solar_eclipses` against a 20-eclipse subset (mirroring `research iterate`'s typical workload) using `params/v1-original/v1.json` at `half_window_hours=6.0` measured **16.572 seconds total** for ~107k calls to `move_planet_tt`. Cumulative time breakdown:

| Cumulative | Function | Notes |
|---|---|---|
| ~42% (7.0s) | `initialize_orbit_parameters` | Called 107,322 times (once per object per `move_system`). Builds `R.from_euler(...) * R.from_euler(...)` for each object on every call. |
| ~41% (6.8s) | `R.from_euler` | 328,857 calls. Most of the time is scipy's `array_api` wrapping (`xp_promote`, `is_torch_array`, `xp_result_type`) — bookkeeping, not math. |
| ~39% (6.5s) | `Rotation.__mul__` | scipy rotation composition during `move_planet_basic`. Same wrapping overhead. |
| ~12% | Everything else | Actual scanner logic, angular separation, position fetches. |

The smoking gun is `tychos_skyfield/baselib.py:380-396`: every `move_system` call re-runs `initialize_orbit_parameters()` for every object, even though that function only reads constructor inputs (`orbit_tilt`, `orbit_center`, `orbit_radius`) and never reads the JD. It's a "reset to factory state" pattern where the factory state is constant. We're rebuilding it ~107k times when it could be cached once.

The remaining time is dominated by scipy `Rotation` machinery in `move_planet_basic`. Replacing scipy with raw numpy would add another ~2-3×, but that risks bit-level golden drift and is deferred to its own PR.

## Architecture

This round ships **three independent, stackable optimizations** plus a one-time submodule wiring fix.

### 1. Cache TychosSystem factory state (math-identical, ~1.7× single-core)

In `tychos_skyfield/baselib.py` (your fork), change `initialize_orbit_parameters` so that on first call it computes the rotation/location/center/radius_vec values *and stores immutable snapshots*. On subsequent calls (from `move_system`'s reset loop), the snapshots are restored via deep copy instead of being recomputed via `R.from_euler`.

Pseudocode:

```python
class PlanetObj:
    def __init__(self, ...):
        ...
        self._init_rotation_cached = None
        self._init_center_cached = None
        self._init_radius_vec_cached = None
        self.initialize_orbit_parameters()

    def initialize_orbit_parameters(self):
        if self._init_rotation_cached is None:
            # First call: compute and cache.
            self._init_rotation_cached = (
                R.from_euler('x', self.orbit_tilt.x, degrees=True) *
                R.from_euler('z', self.orbit_tilt.z, degrees=True)
            )
            self._init_center_cached = np.array(
                [self.orbit_center.x, self.orbit_center.y, self.orbit_center.z],
                dtype=np.float64,
            )
            self._init_radius_vec_cached = np.array([self.orbit_radius, 0.0, 0.0])

        # Restore from cache (each call). Rotation is immutable in scipy so we can
        # share the reference; numpy arrays must be copied because move_planet
        # mutates them.
        self.rotation = self._init_rotation_cached
        self.location = np.array([0.0, 0.0, 0.0])
        self.center = self._init_center_cached.copy()
        self.radius_vec = self._init_radius_vec_cached.copy()
```

**Math safety:** the only behavioral change is "compute once instead of every call." Inputs to the cached computation are constructor params, which never change after `__init__`. Outputs are the same numbers, byte-for-byte. The exact-equality goldens (`pytest -m slow`) are the safety net.

**Submodule constraint:** this lives in `mindaugl/tychos_skyfield`'s code which is already vendored as a git submodule. The user has a fork at `the-real-adammork/tychos_skyfield` which is currently the locally-checked-out remote, but the parent repo's `.gitmodules` still points at the upstream URL. The submodule wiring fix (section 4 below) handles this.

### 2. Multiprocessing across eclipses (math-identical, ~6× on 8 cores)

In `server/services/scanner.py`, parallelize the per-eclipse loop in both `scan_solar_eclipses` and `scan_lunar_eclipses` using `concurrent.futures.ProcessPoolExecutor`.

**Function signature:**

```python
def scan_solar_eclipses(
    params: dict,
    eclipses: list[dict],
    half_window_hours: float = 2.0,
    *,
    max_workers: int | None = None,
    parallel_threshold: int = 8,
) -> list[dict]:
```

- `max_workers=None` → use `max(1, cpu_count() - 1)`. Leaves one core free for the rest of the system.
- `max_workers=1` → forces serial execution (in-process, no pool).
- `parallel_threshold` → if `len(eclipses) < parallel_threshold`, run serially in-process regardless of `max_workers`. Default 8 is "if there's not enough work to bother." Caller can pass any int.

**Short-circuit rule:** parallelize only if `max_workers != 1` AND `len(eclipses) >= parallel_threshold`.

**Worker process pattern:**
- Top-level helper functions in `scanner.py` (no closures, no nested defs):
  - `_init_worker(params, half_window_hours)` — runs once per worker process at startup. Stores a fresh `TychosSystem(params=params)` and the half-window in module-level globals `_WORKER_SYSTEM` and `_WORKER_HALF_WINDOW`.
  - `_scan_one_solar_eclipse(eclipse_dict) -> dict` — reads `_WORKER_SYSTEM` and `_WORKER_HALF_WINDOW` from the module global, runs the per-eclipse work for one entry, returns the row dict. Same shape `scan_solar_eclipses` currently returns.
  - `_scan_one_lunar_eclipse(eclipse_dict) -> dict` — same for lunar (different threshold, different sep math).
- `mp.get_context("spawn").Pool(...)` or `ProcessPoolExecutor(mp_context=spawn_ctx)`. Explicit `spawn` start method for safety on macOS — fork+threads is broken, and the local-deploy worker is a daemon thread inside a larger process.
- `executor.map(_scan_one_*_eclipse, eclipses)` preserves input order, so result row order matches the existing serial version. Goldens still pass.
- If a worker raises, the entire scan raises (existing serial behavior).

### 3. Persistent module-level process pool with per-worker system cache

This is the critical addition for autoresearch. Each call to `evaluate(candidate)` inside `run_search` runs `scan_*_eclipses` once. With a fresh pool per call, the ~200ms pool spawn overhead × 100 evals = ~20s wasted. With a persistent pool, the spawn overhead is paid once per parent process lifetime.

**Design constraints to reconcile:**
1. The pool must persist across calls (the spawn overhead is the whole point of persistence).
2. Search varies `params` between calls, so workers cannot bake params into init time.
3. Sending params with every task is wasteful if the task batch all shares the same params (and they always do — `evaluate(candidate)` calls the scanner once with one params dict for all eclipses in that batch).

**Architecture:**

- **Pool is params-agnostic.** Created lazily on first call, keyed only by `half_window_hours`. Built with `_init_worker(half_window_hours)`. Persists for the lifetime of the parent process.
- **Each task ships `(params, eclipse_dict)`.** Workers cannot bake params into init time, so they must learn them per-task.
- **Workers cache the last `TychosSystem` they constructed (LRU(1)).** If `params` matches the cached one (`is` check first, then equality), the worker reuses the cached system. Otherwise it constructs a new one and replaces the cache.
- **Within a single batch, all eclipses share `params`** → first task in the batch constructs the system, every subsequent task in that worker hits the cache → amortized to one construction per worker per batch.
- **Across batches in a search loop**, each new candidate constructs a new system per worker → one construction per worker per `evaluate()` call. With factory caching from optimization #1, construction is significantly cheaper than today, so this is acceptable.
- **Pool shutdown** is registered with `atexit`. `kill -9` of the parent will leave orphaned workers (recoverable via `pkill`); documented as a known caveat.

**Module-level state in `scanner.py`:**

```python
_POOL: ProcessPoolExecutor | None = None
_POOL_HALF_WINDOW: float | None = None


def _get_or_create_pool(max_workers: int, half_window_hours: float):
    """Return a process pool initialized with the given half_window_hours.

    Persists across calls. Rebuilds only when half_window_hours changes
    (which is per-dataset config and stable within a single process).
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


atexit.register(_shutdown_pool)
```

**Per-worker state (lives inside each subprocess):**

```python
_WORKER_HALF_WINDOW: float | None = None
_WORKER_LAST_PARAMS: dict | None = None
_WORKER_LAST_SYSTEM: TychosSystem | None = None


def _init_worker(half_window_hours: float) -> None:
    global _WORKER_HALF_WINDOW
    _WORKER_HALF_WINDOW = half_window_hours


def _get_worker_system(params: dict) -> TychosSystem:
    """LRU(1) cache: reuse the last TychosSystem if params is unchanged."""
    global _WORKER_LAST_PARAMS, _WORKER_LAST_SYSTEM
    if _WORKER_LAST_PARAMS is params or _WORKER_LAST_PARAMS == params:
        return _WORKER_LAST_SYSTEM
    _WORKER_LAST_SYSTEM = TychosSystem(params=params)
    _WORKER_LAST_PARAMS = params
    return _WORKER_LAST_SYSTEM
```

The `is` check is a fast path: if the orchestrator passes the same dict object across many tasks in one batch (it does, by construction in the parent), the worker skips the deep equality check.

```python
# Module-level state in scanner.py
_POOL: ProcessPoolExecutor | None = None
_POOL_HALF_WINDOW: float | None = None


def _get_or_create_pool(max_workers: int, half_window_hours: float):
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


atexit.register(_shutdown_pool)
```

`half_window_hours` is in the pool key because it doesn't change frequently (it's per-dataset config) and it's cleaner to bake into worker init than into every task. Production callers always pass the same value within a single process, so the key is stable.

**Worker-side cache:**

```python
# Module-level state in scanner.py, accessed only inside worker processes.
_WORKER_HALF_WINDOW: float | None = None
_WORKER_LAST_PARAMS: dict | None = None
_WORKER_LAST_SYSTEM: TychosSystem | None = None


def _init_worker(half_window_hours: float) -> None:
    global _WORKER_HALF_WINDOW
    _WORKER_HALF_WINDOW = half_window_hours


def _get_worker_system(params: dict) -> TychosSystem:
    global _WORKER_LAST_PARAMS, _WORKER_LAST_SYSTEM
    if _WORKER_LAST_PARAMS is params or _WORKER_LAST_PARAMS == params:
        return _WORKER_LAST_SYSTEM
    _WORKER_LAST_SYSTEM = TychosSystem(params=params)
    _WORKER_LAST_PARAMS = params
    return _WORKER_LAST_SYSTEM
```

The `is` check is a fast path: if the orchestrator passes the same dict object across many tasks in one batch (it does), we skip the deep equality check.

### 4. Submodule wiring fix

The local checkout already has `the-real-adammork/tychos_skyfield` configured as a `fork` remote, and the current branch tracks `fork/feature/sync-params-from-tsn`. But `.gitmodules` in the parent repo still points at upstream `mindaugl/tychos_skyfield`. A fresh clone or CI run would pull from upstream and miss any baselib.py changes we land in the fork.

**Steps (one commit on parent repo):**
1. Edit `.gitmodules`: change `url` for `tychos_skyfield` to `https://github.com/the-real-adammork/tychos_skyfield`.
2. `git submodule sync` to push the new URL into `.git/config`.
3. Bump the submodule SHA pointer to the new commit on the fork's branch (this happens naturally when we commit baselib.py changes inside the submodule and then `git add tychos_skyfield` from the parent).
4. Push both: the new commit on the fork's `feature/sync-params-from-tsn` branch, and the parent commit that bumps the submodule pointer.

### 5. Worker.py `TYCHOS_SCANNER_MAX_WORKERS` env var

In `server/worker.py`, add ~3 lines that read the env var and pass it to the scanner:

```python
import os
...
scanner_max_workers = os.environ.get("TYCHOS_SCANNER_MAX_WORKERS")
scanner_max_workers = int(scanner_max_workers) if scanner_max_workers else None
...
results = scan_solar_eclipses(
    params, eclipses,
    half_window_hours=scan_window_hours,
    max_workers=scanner_max_workers,
)
```

When unset, the scanner uses its default (`max(1, cpu_count() - 1)`). Set in launchd plist or shell to throttle the always-on local deploy.

## Data Flow

```
Worker.py / autoresearch CLI / golden tests
  → scan_solar_eclipses(params, eclipses, half_window_hours, max_workers, parallel_threshold)
    → if serial path (max_workers=1 or len < threshold): in-process loop, returns
    → else:
      → _get_or_create_pool(max_workers, half_window_hours)  ← module-level singleton
      → executor.map(_scan_one_solar_eclipse_task, [(params, ecl) for ecl in eclipses])
        → in each worker process:
          → _get_worker_system(params)  ← per-process LRU(1) cache
          → run scan_min_separation against the cached TychosSystem
          → return row dict
      → assemble list (map preserves order)
      → return
```

## File Changes Summary

**Submodule fork (`tychos_skyfield`, branch `feature/sync-params-from-tsn`):**
- `tychos_skyfield/tychos_skyfield/baselib.py` — cache factory state in `PlanetObj.initialize_orbit_parameters` and reset via deep copy.

**Parent repo:**
- `.gitmodules` — point `tychos_skyfield` URL at the fork.
- `server/services/scanner.py` — add multiprocessing orchestration, persistent pool, worker helpers. Existing `scan_solar_eclipses` and `scan_lunar_eclipses` keep their public signatures (with new optional kwargs added at the end).
- `server/worker.py` — read `TYCHOS_SCANNER_MAX_WORKERS` env var, pass to scanner.
- `scripts/benchmark_scanner.py` (new) — small standalone script that times `scan_solar_eclipses` on a 20-event subset, prints before/after comparison numbers. Not run by CI; documents the wall-clock claim.

**Untouched:**
- `tests/test_scanner_golden.py` — exact-equality tests still pass (math is unchanged).
- `tests/test_scanner.py` — fast tests still pass (single-eclipse calls fall below `parallel_threshold` and stay serial).
- `tests/test_jpl_scanner.py` — JPL path is unchanged this round.
- `server/services/jpl_scanner.py` — JPL scanner doesn't get parallelism this round (it runs in `seed.py`, not in the hot path; can be added later if needed).
- `server/research/search.py` — unchanged. The persistent pool inside `scanner.py` automatically benefits all callers.

## Testing Strategy

1. **Default fast suite (`pytest`) must pass.** This is the dev signal.
2. **Golden suite (`pytest -m slow`) must pass with exact equality.** This is the correctness gate. All four golden tests cover Tychos solar/lunar at 6h window; the math hasn't changed, so exact equality must hold.
3. **Smoke test that parallelism is actually engaged.** Add a tiny test in `tests/test_scanner.py` (NOT marked slow) that calls `scan_solar_eclipses` on a small synthetic catalog with `max_workers=2, parallel_threshold=1` and verifies the call returns the expected number of rows. This verifies the multiprocessing path is wired correctly without depending on cores.
4. **Benchmark script** (committed but not invoked by CI). Records before/after timings for the design's wall-clock claim. Used during PR review and as a regression check after follow-up PRs.

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Factory caching breaks math due to a hidden mutable reference (e.g., scipy `Rotation` is not deeply immutable in some edge case). | Goldens. Exact-equality compare on full catalog. |
| `spawn` start method fails on the local-deploy worker because of import side effects in `server/services/scanner.py`. | Keep all module-level state in the file lazy (created on first call, not at import). Test by running the worker against a queued run end-to-end before merging. |
| Process pool leaks workers if the parent crashes or `atexit` doesn't fire. | Use `concurrent.futures.ProcessPoolExecutor` (which is well-behaved) plus an `atexit` handler. Document that `kill -9` of the parent will leave orphaned workers — rare and recoverable via `pkill`. |
| Search performance is dominated by per-task `TychosSystem` construction in workers (since each `evaluate` ships new params). | Optimization #1 (factory caching) makes `TychosSystem(params=params)` significantly cheaper. Per-worker LRU(1) cache amortizes construction across all eclipses in one batch. |
| `TYCHOS_SCANNER_MAX_WORKERS` is set to a too-large value and overwhelms the machine. | Document the env var in worker.py. The scanner caps at `cpu_count()` to prevent thermal disaster. |
| Goldens pass locally but a fresh clone (with the upstream submodule) sees mismatched scanner output. | The submodule wiring fix in section 4 ensures `.gitmodules` points at the fork. Verify by re-cloning the repo into a scratch directory before merging. |

## Open Questions (Resolved During Brainstorming)

- **Scope:** ship factory caching + multiprocessing + persistent pool now; defer scipy rotation replacement and vectorization to follow-up PRs.
- **Worker count:** configurable via `max_workers` parameter, default `max(1, cpu_count() - 1)`. Worker.py reads `TYCHOS_SCANNER_MAX_WORKERS` env var.
- **Where the parallelism lives:** inside `scan_solar_eclipses` / `scan_lunar_eclipses`, public API extended with optional kwargs.
- **Short-circuit threshold:** configurable via `parallel_threshold` parameter, default 8. Combined with `max_workers=1` opt-out.
- **Worker process pattern:** spawn start method, top-level helper functions, module-level globals for per-worker state.
- **Persistent pool:** lifetime is process-wide. Worker init takes only `half_window_hours`. Per-worker LRU(1) cache for `TychosSystem`. Pool key is `half_window_hours` only.
- **Submodule:** point `.gitmodules` at the existing fork, sync, commit fork changes, bump submodule SHA pointer.
- **Goldens regeneration:** not needed for this PR (math is identical). Goldens are the safety net.
- **JPL scanner:** unchanged this round.
- **Search-specific outer-loop parallelism:** not feasible for Nelder-Mead (sequential by nature). The persistent inner-loop pool is the right answer for search performance.
