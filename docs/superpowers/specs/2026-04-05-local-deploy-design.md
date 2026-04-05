# Local Deploy Design

**Date:** 2026-04-05
**Status:** Draft

## Overview

Deploy the Tychos app as a persistent service on a macOS home machine, accessible externally via Cloudflare Tunnel. Uses native launchd for process management and reuses an existing cloudflared tunnel (shared with gowild) by adding a new ingress hostname.

## File Structure

```
local_deploy/
  .env.example              # template with dummy CF values
  setup.sh                  # install deps, build SPA, add tunnel route, load plists
  teardown.sh               # unload plists, remove tunnel route + DNS + Access policy
  com.tychos.server.plist   # uvicorn API server
  com.tychos.worker.plist   # eclipse worker process
```

## Environment Variables (.env.example)

```bash
# Cloudflare Tunnel (reuses existing tunnel on this machine)
CF_API_TOKEN=your-api-token
CF_ACCOUNT_ID=your-account-id
CF_ZONE_ID=your-zone-id
CF_DOMAIN=yourdomain.com
CF_SUBDOMAIN=tychos
CF_ACCESS_EMAIL=user@example.com

# App
TYCHOS_DIR=/Users/you/Projects/tychos
TYCHOS_PORT=8000
```

The real `.env` lives at `local_deploy/.env` (gitignored). `CF_ACCESS_EMAIL` in the example uses a dummy value; the real one is `user@example.com`.

## setup.sh

Idempotent — safe to re-run.

### Steps

1. **Load .env** — source `local_deploy/.env`, abort if missing.

2. **Check prerequisites** — verify `python3.14`, `node`, `npm`, `cloudflared`, `jq` are on PATH.

3. **Python environment** — create/update venv at `tychos_skyfield/.venv`, install deps from `requirements.txt`, `server/requirements.txt`, and `tychos_skyfield/requirements.txt`.

4. **Build admin SPA** — `cd admin && npm install && npm run build`. Output lands in `admin/dist/`.

5. **Initialize database** — `python -c "from server.db import init_db; init_db()"` (runs migrations + seeds param sets from `params/` JSON files).

6. **Detect existing Cloudflare Tunnel** — `GET /accounts/{CF_ACCOUNT_ID}/cfd_tunnel?is_deleted=false` → find the first active tunnel. Store its ID and name.

7. **Add ingress hostname** — `PUT /accounts/{CF_ACCOUNT_ID}/cfd_tunnel/{TUNNEL_ID}/configurations` → add `{CF_SUBDOMAIN}.{CF_DOMAIN}` routing to `http://localhost:{TYCHOS_PORT}`. Preserves existing ingress rules (e.g. gowild). The catch-all `http_status:404` rule stays last.

8. **Create DNS CNAME** — `POST /zones/{CF_ZONE_ID}/dns_records` → `{CF_SUBDOMAIN}.{CF_DOMAIN}` CNAME to `{TUNNEL_ID}.cfargotunnel.com`. Skips if record already exists.

9. **Create Zero Trust Access policy** — `POST /accounts/{CF_ACCOUNT_ID}/access/apps` → gate `{CF_SUBDOMAIN}.{CF_DOMAIN}` behind email verification for `CF_ACCESS_EMAIL`. Skips if app already exists.

10. **Install launchd plists** — copy plists to `~/Library/LaunchAgents/`, substituting `TYCHOS_DIR` and `TYCHOS_PORT` via `sed`. Then `launchctl load` each one.

### Error handling

Each step checks for success before proceeding. If the tunnel or DNS record already exists, it's a no-op. The script prints what it's doing at each step.

## teardown.sh

Reverses setup: unload plists, remove tunnel hostname route, delete DNS CNAME, delete Access app. Does NOT uninstall cloudflared (shared with gowild). Does NOT delete the database.

## Launchd Services

### com.tychos.server.plist

- **Label:** `com.tychos.server`
- **Program:** `TYCHOS_DIR/tychos_skyfield/.venv/bin/uvicorn`
- **Arguments:** `server.app:app --host 127.0.0.1 --port 8000`
- **WorkingDirectory:** `TYCHOS_DIR`
- **EnvironmentVariables:** `PYTHONPATH=tychos_skyfield:tests:.`
- **RunAtLoad:** true
- **KeepAlive:** true (restart on crash)
- **StandardOutPath / StandardErrorPath:** `TYCHOS_DIR/logs/server.log` / `server.err.log`

Note: binds to `127.0.0.1` not `0.0.0.0` — external access goes through cloudflared only.

### com.tychos.worker.plist

- **Label:** `com.tychos.worker`
- **Program:** `TYCHOS_DIR/tychos_skyfield/.venv/bin/python`
- **Arguments:** `-m server.worker`
- **WorkingDirectory:** `TYCHOS_DIR`
- **EnvironmentVariables:** `PYTHONPATH=tychos_skyfield:tests:.`
- **RunAtLoad:** true
- **KeepAlive:** true
- **StandardOutPath / StandardErrorPath:** `TYCHOS_DIR/logs/worker.log` / `worker.err.log`

## Production Server Changes

### FastAPI serves the built SPA

Add to `server/app.py` after all API routers:

```python
# Serve built admin SPA in production
admin_dist = Path(__file__).parent.parent / "admin" / "dist"
if admin_dist.is_dir():
    app.mount("/assets", StaticFiles(directory=admin_dist / "assets"), name="static-assets")

    @app.get("/{path:path}")
    async def spa_fallback(path: str):
        """Serve index.html for all non-API routes (SPA client routing)."""
        return FileResponse(admin_dist / "index.html")
```

API routes are registered first, so `/api/*` takes priority. The SPA fallback only catches non-API paths.

### CORS

Update CORS to include the tunnel domain:

```python
allow_origins=[
    "http://localhost:5173",                        # dev
    f"https://{CF_SUBDOMAIN}.{CF_DOMAIN}",         # production
]
```

Or simplify: if `admin/dist` exists (production mode), CORS isn't needed since the SPA is same-origin. Could conditionally skip the middleware.

### Uvicorn

Remove `--reload` (no file watching in production). Add `--host 127.0.0.1` to bind only to localhost.

## Tunnel Architecture (Shared with Gowild)

```
Internet
  │
  ├── gowild.yourdomain.com ──┐
  │                                 │
  └── tychos.yourdomain.com ──┤
                                    │
                               cloudflared (single process)
                                    │
                    ┌───────────────┼───────────────┐
                    │               │               │
              localhost:3000  localhost:8000    (future apps)
              (gowild)        (tychos)
```

Single cloudflared service, multiple ingress rules. Each app manages its own route during setup/teardown.

## Future: Autoresearch

When autoresearch is added:
- A new `com.tychos.autoresearch.plist` follows the same pattern
- Triggered via a queued job from the admin UI (like eclipse runs)
- The worker picks up autoresearch jobs from the same queue, or a dedicated autoresearch worker polls a separate queue
- No changes to the tunnel or deploy structure needed — it's just another local process

## Gitignore Additions

```
local_deploy/.env
logs/
```

## What This Design Does NOT Cover

- Remote/cloud deployment (future `remote_deploy/` directory)
- SSL certificates (Cloudflare handles TLS termination)
- Database backups (could be a future cron job)
- Log rotation (macOS `newsyslog` or manual for now)
