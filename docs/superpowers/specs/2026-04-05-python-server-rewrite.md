# Python Server + React SPA Rewrite

## Overview

Replace the Next.js app with a FastAPI Python server + Vite React SPA. The Python server owns all computation (eclipse scanning), database writes, and API. The React frontend keeps all existing shadcn components and fetches from the Python API.

## Why

- One server process instead of two (Node + Python)
- Computation (tychos_skyfield) and API live in the same Python process — no subprocess spawning or inter-process HTTP
- Database writes happen in Python directly — no Prisma/sqlite3 mismatch
- Simpler deployment

## Architecture

```
Browser (React SPA via Vite)
    ↓ fetch()
FastAPI (Python)
    ├── API routes (auth, params, runs, results, compare)
    ├── Computation (eclipse scanning via tychos_skyfield)
    └── SQLite (direct sqlite3 or SQLAlchemy)
```

### Layers inside the Python server

```
server/
  api/          — FastAPI route handlers (thin, just HTTP concerns)
  services/     — Business logic (computation, database writes)
    scanner.py  — Eclipse scanning (imports tychos_skyfield, helpers)
    db.py       — Database reads and writes
  models.py     — SQLite schema / table definitions
  auth.py       — Session management
  app.py        — FastAPI app setup, serves React static files
```

### Computation / Database Decoupling

The scanner produces results as a list of dicts in memory. It does NOT write to the database. A separate service handles batching results into the database after the scan completes.

```python
# scanner.py — pure computation, no DB
def scan_solar_eclipses(params: dict, eclipses: list) -> list[dict]:
    """Returns list of result dicts. No side effects."""
    system = TychosSystem(params=params)
    results = []
    for eclipse in eclipses:
        result = scan_one_solar(system, eclipse)
        results.append(result)
    return results

# db.py — batch write
def save_eclipse_results(run_id: int, results: list[dict]):
    """Writes all results in one transaction."""
    conn = get_connection()
    conn.executemany("INSERT INTO ...", results)
    conn.commit()
```

The run endpoint flow:
1. API creates a Run row with status "queued"
2. Background thread picks it up, sets "running"
3. Calls `scanner.scan_solar_eclipses()` — pure computation, returns list
4. Calls `db.save_eclipse_results()` — one batch write
5. Updates Run to "done"

### Tests

Tests only test the computation layer (scanner.py). They import the scanner directly and assert on the returned results. No database involvement in tests.

```python
# tests/test_scanner.py
def test_solar_eclipse_detected():
    params = load_json("params/v1-original.json")
    eclipses = [{"julian_day_tt": 2457987.268519, ...}]  # 2017-08-21 total solar
    results = scan_solar_eclipses(params, eclipses)
    assert results[0]["detected"] == True
    assert results[0]["min_separation_arcmin"] < 48.0
```

Existing smoke tests (angular separation, false positives) remain as-is — they test helpers.py which the scanner uses.

## React SPA Changes

### Build tool
- Next.js → Vite + React
- Same TypeScript, same Tailwind, same shadcn components

### Routing
- `next/navigation` → `react-router-dom`
- `next/link` → `react-router-dom` `<Link>`
- Server components → all client components (they already fetch via API)

### Font
- `next/font` → CSS `@import` for Inter from Google Fonts

### Pages (no changes to component logic)
- All existing shadcn UI components work unchanged
- All existing page components work — just swap routing imports
- Remove `layout.tsx` server component, replace with a client-side `App.tsx` with router + auth context

### API base URL
- In dev: Vite proxy `/api` → `http://localhost:8000/api`
- In prod: FastAPI serves the built React files from `dist/`

## Database

Same SQLite schema as before (User, Session, ParamSet, Run, EclipseResult). But instead of Prisma, use raw `sqlite3` or SQLAlchemy. The schema is simple enough that raw sqlite3 with a thin helper layer is fine.

## File Layout

```
server/
  app.py                    # FastAPI app, serves SPA in prod
  auth.py                   # password hashing, sessions, cookie middleware
  models.py                 # schema init, table creation
  db.py                     # connection helper, batch inserts
  services/
    scanner.py              # eclipse scanning (pure computation)
  api/
    auth_routes.py          # register, login, logout
    params_routes.py        # CRUD + fork
    runs_routes.py          # list, create (queues job), get single
    results_routes.py       # paginated eclipse results
    compare_routes.py       # side-by-side comparison
  worker.py                 # background thread that processes queued runs

admin/                      # React SPA (replaces Next.js)
  package.json
  vite.config.ts
  tsconfig.json
  index.html
  src/
    main.tsx                # entry point, router setup
    App.tsx                 # layout with sidebar + auth context
    pages/                  # same pages, swapped routing
    components/             # unchanged shadcn + feature components
    lib/                    # utils

tests/
  conftest.py
  helpers.py                # angular separation, scan functions (unchanged)
  test_smoke.py             # angular separation + sanity checks (unchanged)
  test_scanner.py           # tests for server/services/scanner.py
  data/
    solar_eclipses.json
    lunar_eclipses.json

params/
  v1-original.json
```

## What Gets Deleted

- `admin/src/app/api/` — all Next.js API routes (replaced by FastAPI)
- `admin/src/lib/worker.ts` — Node background worker
- `admin/src/instrumentation.ts` — Node worker startup
- `admin/src/lib/db.ts` — Prisma singleton
- `admin/src/lib/auth.ts` — Node auth helpers
- `admin/src/generated/prisma/` — Prisma generated client
- `admin/prisma/` — Prisma schema and seed
- `tests/db.py` — Python db helpers (replaced by server/db.py)
- `tests/run_eclipses.py` — standalone runner (replaced by server/services/scanner.py + worker)

## What Gets Kept (moved)

- All `admin/src/components/` — shadcn UI + feature components → `admin/src/components/`
- All page content — extracted from Next.js pages → `admin/src/pages/`
- `tests/helpers.py` — angular separation, scan functions (imported by scanner.py)
- `tests/test_smoke.py` — sanity checks
- `tests/data/*.json` — eclipse catalog data
