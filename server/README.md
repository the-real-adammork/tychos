# Server

[← Back to README](../README.md)

The Python backend for the Tychos eclipse test suite. FastAPI app + SQLite + a background worker that runs eclipse scans against parameter sets.

## Components

```
server/
├── app.py              # FastAPI entrypoint, CORS, SPA fallback
├── auth.py             # bcrypt password hashing, cookie sessions
├── db.py               # sqlite + aiosqlite connection helpers, migration runner
├── seed.py             # initial admin user, datasets, catalog, JPL & predicted refs
├── worker.py           # background worker that polls the runs queue and executes scans
├── params_store.py     # disk persistence for params/<name>/v<N>.json files
├── requirements.txt    # FastAPI, uvicorn, bcrypt, aiosqlite, etc.
├── migrations/         # numbered .sql files applied in order
├── services/
│   ├── scanner.py             # two-pass minimum-separation scan over the Tychos system
│   └── predicted_geometry.py  # catalog gamma/magnitude → predicted geometry
└── api/
    ├── auth_routes.py       # /api/auth/{register,login,logout,me}
    ├── params_routes.py     # /api/params/...
    ├── runs_routes.py       # /api/runs
    ├── results_routes.py    # /api/results/{run_id}, /saros, /{result_id}
    ├── compare_routes.py    # /api/compare, /api/compare/saros
    ├── dashboard_routes.py  # /api/dashboard
    └── dataset_routes.py    # /api/datasets
```

## Running

### Dev server

```bash
source tychos_skyfield/.venv/bin/activate
PYTHONPATH=tychos_skyfield:tests:. uvicorn server.app:app --port 8000 --reload
```

### Worker

The worker runs separately and polls the `runs` table for queued runs:

```bash
PYTHONPATH=tychos_skyfield:tests:. python -m server.worker
```

You can also start everything (API server + worker + admin SPA dev server) at once with `./dev.sh` from the repo root.

## Database

SQLite database stored at `results/tychos_results.db`. Schema is defined by ordered SQL files in `server/migrations/`. The first call to `init_db()` (which `app.py` runs in its FastAPI lifespan) applies any new migrations and then runs `seed.py` to populate datasets, the eclipse catalog, the JPL reference table, and the predicted reference table.

### Key tables

| Table | Purpose |
|---|---|
| `users`, `sessions` | bcrypt-hashed users, cookie-keyed sessions |
| `datasets` | One row per eclipse catalog (`solar_eclipse`, `lunar_eclipse`) |
| `eclipse_catalog` | Every NASA catalog record, keyed by `dataset_id` + `julian_day_tt` |
| `predicted_reference` | Catalog-derived per-eclipse expected geometry (no Skyfield, no Tychos) |
| `jpl_reference` | Pre-computed JPL DE440s Sun & Moon positions for every catalog eclipse |
| `param_sets` + `param_versions` | Versioned orbital parameter sets, owned by users |
| `runs` | Queue of (param_version, dataset) pairs to scan |
| `eclipse_results` | One row per scanned eclipse with `tychos_error_arcmin`, `jpl_error_arcmin`, etc. |

## Environment Variables

| Var | Required | Purpose |
|---|---|---|
| `TYCHOS_ADMIN_USER` | First boot only | Email for the seeded admin user |
| `TYCHOS_ADMIN_PASSWORD` | First boot only | Password for the seeded admin user |

If no users exist yet and these are unset, `_seed_admin_user()` raises a `RuntimeError` rather than creating a default account. After the first user exists subsequent boots no-op.

## Auth model

- `POST /api/auth/register` is open — anyone can create an account.
- Sessions are cookies (`tychos_session`, httponly, samesite=lax, 30-day lifetime).
- `require_user` is a FastAPI dependency that returns the authenticated user dict or raises 401.
- Owner-level checks live in individual route handlers (e.g. only the param set owner can delete it).

This means **the server alone does not enforce access control**. In production you must put it behind an external auth gate — see [`local_deploy/README.md`](../local_deploy/README.md) for the Cloudflare Access setup we use.
