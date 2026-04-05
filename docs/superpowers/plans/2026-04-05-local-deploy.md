# Local Deploy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy the Tychos app as a persistent macOS launchd service accessible via Cloudflare Tunnel, sharing the existing tunnel with gowild.

**Architecture:** Two launchd user agents (uvicorn API server + eclipse worker) running under the current user. FastAPI serves the built React SPA as static files in production. Cloudflare Tunnel adds a new ingress hostname to the existing tunnel. Setup and teardown are idempotent shell scripts.

**Tech Stack:** launchd, cloudflared, Cloudflare API (tunnels, DNS, Access), FastAPI StaticFiles, Vite build

**Spec:** `docs/superpowers/specs/2026-04-05-local-deploy-design.md`

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `local_deploy/.env.example` | Template env vars with dummy values |
| Create | `local_deploy/setup.sh` | Idempotent setup: deps, build, CF tunnel, launchd |
| Create | `local_deploy/teardown.sh` | Reverse: unload plists, remove CF route/DNS/Access |
| Create | `local_deploy/com.tychos.server.plist` | launchd template for uvicorn |
| Create | `local_deploy/com.tychos.worker.plist` | launchd template for worker |
| Modify | `server/app.py` | Add SPA static file serving + fallback route |
| Modify | `.gitignore` | Add `local_deploy/.env` and `logs/` |

---

### Task 1: Gitignore and .env.example

**Files:**
- Modify: `.gitignore`
- Create: `local_deploy/.env.example`

- [ ] **Step 1: Add deploy ignores to .gitignore**

Append to `.gitignore`:

```
local_deploy/.env
logs/
```

- [ ] **Step 2: Create .env.example**

Create `local_deploy/.env.example`:

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

- [ ] **Step 3: Commit**

```bash
git add .gitignore local_deploy/.env.example
git commit -m "chore(deploy): add .env.example and gitignore for local deploy"
```

---

### Task 2: FastAPI serves the built SPA

**Files:**
- Modify: `server/app.py`

- [ ] **Step 1: Verify current app.py**

Read `server/app.py` to confirm the current state. It currently:
- Has CORS allowing `http://localhost:5173` only
- Does NOT serve static files
- Does NOT have a SPA fallback route

- [ ] **Step 2: Add SPA serving after all routers**

Add the following after the `app.include_router(dashboard_router)` line in `server/app.py`:

```python
from fastapi.responses import FileResponse

# Serve built admin SPA in production (admin/dist/ exists after `npm run build`)
_admin_dist = Path(__file__).parent.parent / "admin" / "dist"
if _admin_dist.is_dir():
    app.mount("/assets", StaticFiles(directory=_admin_dist / "assets"), name="static-assets")

    @app.get("/{path:path}")
    async def spa_fallback(path: str):
        """Serve index.html for all non-API routes (SPA client routing)."""
        return FileResponse(_admin_dist / "index.html")
```

This is conditional — the `if` block only activates when `admin/dist/` exists (i.e. after a production build). During dev, `admin/dist/` is gitignored and won't exist unless you've run `npm run build`, so the dev workflow is unaffected.

- [ ] **Step 3: Verify dev mode still works**

Run the server in dev mode (without `admin/dist/`). Confirm `/api/dashboard` still returns JSON and the CORS header is present for the Vite dev server.

```bash
cd /Users/adam/Projects/tychos
source tychos_skyfield/.venv/bin/activate
PYTHONPATH=tychos_skyfield:tests:. uvicorn server.app:app --port 8000 &
sleep 2
curl -s http://localhost:8000/api/dashboard | head -c 200
kill %1
```

Expected: JSON response from the dashboard route.

- [ ] **Step 4: Verify production mode works**

Build the SPA, then test that uvicorn serves it:

```bash
cd /Users/adam/Projects/tychos/admin && npm run build && cd ..
source tychos_skyfield/.venv/bin/activate
PYTHONPATH=tychos_skyfield:tests:. uvicorn server.app:app --port 8000 &
sleep 2
# API still works
curl -s http://localhost:8000/api/dashboard | head -c 100
# SPA index.html served for non-API routes
curl -s http://localhost:8000/runs | head -c 200
# Static assets served
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/assets/index-*.js
kill %1
```

Expected: API returns JSON, `/runs` returns HTML (`<!DOCTYPE html>`), assets return 200.

- [ ] **Step 5: Commit**

```bash
git add server/app.py
git commit -m "feat(server): serve built SPA static files in production"
```

---

### Task 3: Launchd plist templates

**Files:**
- Create: `local_deploy/com.tychos.server.plist`
- Create: `local_deploy/com.tychos.worker.plist`

- [ ] **Step 1: Create server plist**

Create `local_deploy/com.tychos.server.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.tychos.server</string>

    <key>ProgramArguments</key>
    <array>
        <string>__TYCHOS_DIR__/tychos_skyfield/.venv/bin/uvicorn</string>
        <string>server.app:app</string>
        <string>--host</string>
        <string>127.0.0.1</string>
        <string>--port</string>
        <string>__TYCHOS_PORT__</string>
    </array>

    <key>WorkingDirectory</key>
    <string>__TYCHOS_DIR__</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PYTHONPATH</key>
        <string>tychos_skyfield:tests:.</string>
        <key>PATH</key>
        <string>__TYCHOS_DIR__/tychos_skyfield/.venv/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <true/>

    <key>StandardOutPath</key>
    <string>__TYCHOS_DIR__/logs/server.log</string>

    <key>StandardErrorPath</key>
    <string>__TYCHOS_DIR__/logs/server.err.log</string>
</dict>
</plist>
```

Note: `__TYCHOS_DIR__` and `__TYCHOS_PORT__` are placeholders that `setup.sh` substitutes via `sed`.

- [ ] **Step 2: Create worker plist**

Create `local_deploy/com.tychos.worker.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.tychos.worker</string>

    <key>ProgramArguments</key>
    <array>
        <string>__TYCHOS_DIR__/tychos_skyfield/.venv/bin/python</string>
        <string>-m</string>
        <string>server.worker</string>
    </array>

    <key>WorkingDirectory</key>
    <string>__TYCHOS_DIR__</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PYTHONPATH</key>
        <string>tychos_skyfield:tests:.</string>
        <key>PATH</key>
        <string>__TYCHOS_DIR__/tychos_skyfield/.venv/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <true/>

    <key>StandardOutPath</key>
    <string>__TYCHOS_DIR__/logs/worker.log</string>

    <key>StandardErrorPath</key>
    <string>__TYCHOS_DIR__/logs/worker.err.log</string>
</dict>
</plist>
```

- [ ] **Step 3: Commit**

```bash
git add local_deploy/com.tychos.server.plist local_deploy/com.tychos.worker.plist
git commit -m "chore(deploy): add launchd plist templates for server and worker"
```

---

### Task 4: setup.sh

**Files:**
- Create: `local_deploy/setup.sh`

- [ ] **Step 1: Create setup.sh**

Create `local_deploy/setup.sh`:

```bash
#!/bin/bash
set -euo pipefail

# ── Load config ────���─────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env"

if [ ! -f "$ENV_FILE" ]; then
    echo "ERROR: ${ENV_FILE} not found. Copy .env.example to .env and fill in values."
    exit 1
fi

source "$ENV_FILE"

# Validate required vars
for var in CF_API_TOKEN CF_ACCOUNT_ID CF_ZONE_ID CF_DOMAIN CF_SUBDOMAIN CF_ACCESS_EMAIL TYCHOS_DIR TYCHOS_PORT; do
    if [ -z "${!var:-}" ]; then
        echo "ERROR: $var is not set in .env"
        exit 1
    fi
done

HOSTNAME="${CF_SUBDOMAIN}.${CF_DOMAIN}"
CF_API="https://api.cloudflare.com/client/v4"
LOGS_DIR="${TYCHOS_DIR}/logs"

echo "=== Tychos Local Deploy ==="
echo "  App:    ${HOSTNAME}"
echo "  Port:   ${TYCHOS_PORT}"
echo "  Dir:    ${TYCHOS_DIR}"
echo ""

# ── Check prerequisites ───���──────────────────────────────────
echo "[1/9] Checking prerequisites..."
for cmd in python3 node npm cloudflared jq; do
    if ! command -v "$cmd" &>/dev/null; then
        echo "ERROR: $cmd not found. Install it first."
        exit 1
    fi
done
echo "  All prerequisites found."

# ── Python environment ────────────────────────────────────────
echo "[2/9] Setting up Python environment..."
VENV_DIR="${TYCHOS_DIR}/tychos_skyfield/.venv"
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
fi
source "${VENV_DIR}/bin/activate"
pip install -q -r "${TYCHOS_DIR}/requirements.txt"
pip install -q -r "${TYCHOS_DIR}/server/requirements.txt"
pip install -q -r "${TYCHOS_DIR}/tychos_skyfield/requirements.txt"
echo "  Python deps installed."

# ── Build admin SPA ────��───────────────────────────────��──────
echo "[3/9] Building admin SPA..."
cd "${TYCHOS_DIR}/admin"
npm install --silent
npm run build
cd "${TYCHOS_DIR}"
echo "  SPA built to admin/dist/."

# ── Initialize database ──────────────────────────────────────
echo "[4/9] Initializing database..."
cd "${TYCHOS_DIR}"
PYTHONPATH=tychos_skyfield:tests:. python3 -c "from server.db import init_db; init_db()"
echo "  Database ready."

# ── Create logs directory ─────────────────────────────────────
mkdir -p "$LOGS_DIR"

# ── Verify CF token ───��──────────────────────────────────���───
echo "[5/9] Verifying Cloudflare API token..."
VERIFY_RESP=$(curl -s "${CF_API}/accounts/${CF_ACCOUNT_ID}/tokens/verify" \
    -H "Authorization: Bearer ${CF_API_TOKEN}")
if [ "$(echo "$VERIFY_RESP" | jq -r '.success')" != "true" ]; then
    echo "ERROR: Cloudflare API token verification failed."
    echo "$VERIFY_RESP" | jq '.errors'
    exit 1
fi
echo "  Token valid."

# ── Detect existing tunnel ────────────────────────────────────
echo "[6/9] Detecting existing Cloudflare Tunnel..."
TUNNELS_RESP=$(curl -s "${CF_API}/accounts/${CF_ACCOUNT_ID}/cfd_tunnel?is_deleted=false" \
    -H "Authorization: Bearer ${CF_API_TOKEN}")
TUNNEL_ID=$(echo "$TUNNELS_RESP" | jq -r '.result[0].id // empty')
TUNNEL_NAME=$(echo "$TUNNELS_RESP" | jq -r '.result[0].name // empty')

if [ -z "$TUNNEL_ID" ]; then
    echo "  No existing tunnel found. Creating one..."
    CREATE_RESP=$(curl -s -X POST \
        "${CF_API}/accounts/${CF_ACCOUNT_ID}/cfd_tunnel" \
        -H "Authorization: Bearer ${CF_API_TOKEN}" \
        -H "Content-Type: application/json" \
        --data "{\"name\":\"${CF_SUBDOMAIN}\",\"config_src\":\"cloudflare\",\"tunnel_secret\":\"$(openssl rand -base64 32)\"}")
    TUNNEL_ID=$(echo "$CREATE_RESP" | jq -r '.result.id')
    TUNNEL_NAME=$(echo "$CREATE_RESP" | jq -r '.result.name')

    if [ -z "$TUNNEL_ID" ] || [ "$TUNNEL_ID" = "null" ]; then
        echo "ERROR: Failed to create tunnel."
        echo "$CREATE_RESP" | jq '.errors'
        exit 1
    fi

    # Install cloudflared service since this is a fresh tunnel
    echo "  Retrieving tunnel token..."
    TOKEN_RESP=$(curl -s "${CF_API}/accounts/${CF_ACCOUNT_ID}/cfd_tunnel/${TUNNEL_ID}/token" \
        -H "Authorization: Bearer ${CF_API_TOKEN}")
    TUNNEL_TOKEN=$(echo "$TOKEN_RESP" | jq -r '.result // empty')
    if [ -z "$TUNNEL_TOKEN" ]; then
        echo "ERROR: Failed to retrieve tunnel token."
        exit 1
    fi
    echo "  Installing cloudflared service..."
    sudo cloudflared service install "$TUNNEL_TOKEN"
    echo "  Tunnel created and cloudflared installed."
else
    echo "  Found tunnel: ${TUNNEL_NAME} (${TUNNEL_ID})"
fi

# ── Add ingress hostname ──────��───────────────────────────────
echo "[7/9] Adding ingress hostname for ${HOSTNAME}..."

# Get current tunnel config to preserve existing ingress rules
CURRENT_CONFIG=$(curl -s "${CF_API}/accounts/${CF_ACCOUNT_ID}/cfd_tunnel/${TUNNEL_ID}/configurations" \
    -H "Authorization: Bearer ${CF_API_TOKEN}")

# Build new ingress: existing rules (minus catch-all) + tychos rule + catch-all
# Remove any existing rule for our hostname to make this idempotent
EXISTING_RULES=$(echo "$CURRENT_CONFIG" | jq -r '[.result.config.ingress[] | select(.hostname != null and .hostname != "'"${HOSTNAME}"'")]')
TYCHOS_RULE="{\"hostname\":\"${HOSTNAME}\",\"service\":\"http://localhost:${TYCHOS_PORT}\"}"
CATCHALL="{\"service\":\"http_status:404\"}"

NEW_INGRESS=$(echo "${EXISTING_RULES}" | jq ". + [${TYCHOS_RULE}, ${CATCHALL}]")

INGRESS_RESP=$(curl -s -X PUT \
    "${CF_API}/accounts/${CF_ACCOUNT_ID}/cfd_tunnel/${TUNNEL_ID}/configurations" \
    -H "Authorization: Bearer ${CF_API_TOKEN}" \
    -H "Content-Type: application/json" \
    --data "{\"config\":{\"ingress\":${NEW_INGRESS}}}")

if [ "$(echo "$INGRESS_RESP" | jq -r '.success')" != "true" ]; then
    echo "ERROR: Failed to update tunnel ingress."
    echo "$INGRESS_RESP" | jq '.errors'
    exit 1
fi
echo "  Ingress rule added."

# ── Create DNS CNAME ─────────────────────────────────────��────
echo "[8/9] Creating DNS record for ${HOSTNAME}..."
EXISTING_DNS=$(curl -s "${CF_API}/zones/${CF_ZONE_ID}/dns_records?type=CNAME&name=${HOSTNAME}" \
    -H "Authorization: Bearer ${CF_API_TOKEN}")
EXISTING_DNS_ID=$(echo "$EXISTING_DNS" | jq -r '.result[0].id // empty')

CNAME_CONTENT="${TUNNEL_ID}.cfargotunnel.com"

if [ -n "$EXISTING_DNS_ID" ]; then
    # Update existing record
    curl -s -X PUT \
        "${CF_API}/zones/${CF_ZONE_ID}/dns_records/${EXISTING_DNS_ID}" \
        -H "Authorization: Bearer ${CF_API_TOKEN}" \
        -H "Content-Type: application/json" \
        --data "{\"type\":\"CNAME\",\"proxied\":true,\"name\":\"${HOSTNAME}\",\"content\":\"${CNAME_CONTENT}\"}" > /dev/null
    echo "  DNS record updated."
else
    DNS_RESP=$(curl -s -X POST \
        "${CF_API}/zones/${CF_ZONE_ID}/dns_records" \
        -H "Authorization: Bearer ${CF_API_TOKEN}" \
        -H "Content-Type: application/json" \
        --data "{\"type\":\"CNAME\",\"proxied\":true,\"name\":\"${HOSTNAME}\",\"content\":\"${CNAME_CONTENT}\"}")
    if [ "$(echo "$DNS_RESP" | jq -r '.success')" != "true" ]; then
        echo "ERROR: Failed to create DNS record."
        echo "$DNS_RESP" | jq '.errors'
        exit 1
    fi
    echo "  DNS record created."
fi

# ── Create Zero Trust Access policy ──────────────────────────
echo "[9/9] Setting up Zero Trust Access..."

# Check if Access app already exists
EXISTING_APPS=$(curl -s "${CF_API}/accounts/${CF_ACCOUNT_ID}/access/apps" \
    -H "Authorization: Bearer ${CF_API_TOKEN}")
APP_ID=$(echo "$EXISTING_APPS" | jq -r ".result[] | select(.domain == \"${HOSTNAME}\") | .id" 2>/dev/null || echo "")

if [ -z "$APP_ID" ]; then
    APP_RESP=$(curl -s -X POST \
        "${CF_API}/accounts/${CF_ACCOUNT_ID}/access/apps" \
        -H "Authorization: Bearer ${CF_API_TOKEN}" \
        -H "Content-Type: application/json" \
        --data "{\"type\":\"self_hosted\",\"name\":\"Tychos\",\"domain\":\"${HOSTNAME}\",\"session_duration\":\"24h\"}")
    APP_ID=$(echo "$APP_RESP" | jq -r '.result.id')

    if [ -z "$APP_ID" ] || [ "$APP_ID" = "null" ]; then
        echo "ERROR: Failed to create Access app."
        echo "$APP_RESP" | jq '.errors'
        exit 1
    fi

    # Create email policy
    curl -s -X POST \
        "${CF_API}/accounts/${CF_ACCOUNT_ID}/access/apps/${APP_ID}/policies" \
        -H "Authorization: Bearer ${CF_API_TOKEN}" \
        -H "Content-Type: application/json" \
        --data "{\"name\":\"Allow owner\",\"decision\":\"allow\",\"include\":[{\"email\":{\"email\":\"${CF_ACCESS_EMAIL}\"}}]}" > /dev/null
    echo "  Access app and policy created."
else
    echo "  Access app already exists."
fi

# ── Install launchd plists ────────────────────────────────────
echo ""
echo "Installing launchd services..."

LAUNCH_AGENTS_DIR="${HOME}/Library/LaunchAgents"
mkdir -p "$LAUNCH_AGENTS_DIR"

for plist in com.tychos.server.plist com.tychos.worker.plist; do
    LABEL="${plist%.plist}"

    # Unload if already loaded (ignore errors)
    launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true

    # Substitute placeholders and copy
    sed -e "s|__TYCHOS_DIR__|${TYCHOS_DIR}|g" \
        -e "s|__TYCHOS_PORT__|${TYCHOS_PORT}|g" \
        "${SCRIPT_DIR}/${plist}" > "${LAUNCH_AGENTS_DIR}/${plist}"

    # Load the service
    launchctl bootstrap "gui/$(id -u)" "${LAUNCH_AGENTS_DIR}/${plist}"
    echo "  Loaded ${LABEL}"
done

echo ""
echo "=== Deploy complete ==="
echo "  Server:  http://localhost:${TYCHOS_PORT}"
echo "  Tunnel:  https://${HOSTNAME}"
echo "  Logs:    ${LOGS_DIR}/"
echo ""
echo "  Manage services:"
echo "    launchctl kickstart gui/$(id -u)/com.tychos.server"
echo "    launchctl kill SIGTERM gui/$(id -u)/com.tychos.server"
echo "    tail -f ${LOGS_DIR}/server.log"
```

- [ ] **Step 2: Make executable**

```bash
chmod +x local_deploy/setup.sh
```

- [ ] **Step 3: Commit**

```bash
git add local_deploy/setup.sh
git commit -m "feat(deploy): add setup.sh for local macOS deployment"
```

---

### Task 5: teardown.sh

**Files:**
- Create: `local_deploy/teardown.sh`

- [ ] **Step 1: Create teardown.sh**

Create `local_deploy/teardown.sh`:

```bash
#!/bin/bash
set -euo pipefail

# ── Load config ──────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env"

if [ ! -f "$ENV_FILE" ]; then
    echo "ERROR: ${ENV_FILE} not found."
    exit 1
fi

source "$ENV_FILE"

HOSTNAME="${CF_SUBDOMAIN}.${CF_DOMAIN}"
CF_API="https://api.cloudflare.com/client/v4"

echo "=== Tychos Local Teardown ==="
echo "  Removing: ${HOSTNAME}"
echo ""

# ── Unload launchd services ───���───────────────────────────────
echo "[1/4] Unloading launchd services..."
for label in com.tychos.server com.tychos.worker; do
    launchctl bootout "gui/$(id -u)/${label}" 2>/dev/null && echo "  Unloaded ${label}" || echo "  ${label} not loaded (skipped)"
    rm -f "${HOME}/Library/LaunchAgents/${label}.plist"
done

# ── Remove ingress hostname ────────────���──────────────────────
echo "[2/4] Removing tunnel ingress for ${HOSTNAME}..."

# Find tunnel
TUNNELS_RESP=$(curl -s "${CF_API}/accounts/${CF_ACCOUNT_ID}/cfd_tunnel?is_deleted=false" \
    -H "Authorization: Bearer ${CF_API_TOKEN}")
TUNNEL_ID=$(echo "$TUNNELS_RESP" | jq -r '.result[0].id // empty')

if [ -n "$TUNNEL_ID" ]; then
    CURRENT_CONFIG=$(curl -s "${CF_API}/accounts/${CF_ACCOUNT_ID}/cfd_tunnel/${TUNNEL_ID}/configurations" \
        -H "Authorization: Bearer ${CF_API_TOKEN}")

    # Remove our hostname, keep everything else (including catch-all)
    REMAINING_RULES=$(echo "$CURRENT_CONFIG" | jq '[.result.config.ingress[] | select(.hostname != "'"${HOSTNAME}"'")]')

    curl -s -X PUT \
        "${CF_API}/accounts/${CF_ACCOUNT_ID}/cfd_tunnel/${TUNNEL_ID}/configurations" \
        -H "Authorization: Bearer ${CF_API_TOKEN}" \
        -H "Content-Type: application/json" \
        --data "{\"config\":{\"ingress\":${REMAINING_RULES}}}" > /dev/null
    echo "  Ingress rule removed."
else
    echo "  No tunnel found (skipped)."
fi

# ── Delete DNS CNAME ──────────────────────────────────────────
echo "[3/4] Removing DNS record for ${HOSTNAME}..."
EXISTING_DNS=$(curl -s "${CF_API}/zones/${CF_ZONE_ID}/dns_records?type=CNAME&name=${HOSTNAME}" \
    -H "Authorization: Bearer ${CF_API_TOKEN}")
DNS_ID=$(echo "$EXISTING_DNS" | jq -r '.result[0].id // empty')

if [ -n "$DNS_ID" ]; then
    curl -s -X DELETE \
        "${CF_API}/zones/${CF_ZONE_ID}/dns_records/${DNS_ID}" \
        -H "Authorization: Bearer ${CF_API_TOKEN}" > /dev/null
    echo "  DNS record deleted."
else
    echo "  No DNS record found (skipped)."
fi

# ── Delete Access app ─────────────────────────────────────────
echo "[4/4] Removing Zero Trust Access app..."
EXISTING_APPS=$(curl -s "${CF_API}/accounts/${CF_ACCOUNT_ID}/access/apps" \
    -H "Authorization: Bearer ${CF_API_TOKEN}")
APP_ID=$(echo "$EXISTING_APPS" | jq -r ".result[] | select(.domain == \"${HOSTNAME}\") | .id" 2>/dev/null || echo "")

if [ -n "$APP_ID" ]; then
    curl -s -X DELETE \
        "${CF_API}/accounts/${CF_ACCOUNT_ID}/access/apps/${APP_ID}" \
        -H "Authorization: Bearer ${CF_API_TOKEN}" > /dev/null
    echo "  Access app deleted."
else
    echo "  No Access app found (skipped)."
fi

echo ""
echo "=== Teardown complete ==="
echo "  Note: cloudflared service was NOT removed (shared with other apps)."
echo "  Note: Database was NOT deleted (${TYCHOS_DIR}/results/)."
```

- [ ] **Step 2: Make executable**

```bash
chmod +x local_deploy/teardown.sh
```

- [ ] **Step 3: Commit**

```bash
git add local_deploy/teardown.sh
git commit -m "feat(deploy): add teardown.sh for local macOS deployment"
```

---

### Task 6: End-to-end test

- [ ] **Step 1: Create .env from .env.example**

```bash
cp local_deploy/.env.example local_deploy/.env
```

Edit `local_deploy/.env` with real values:
- `CF_API_TOKEN`, `CF_ACCOUNT_ID`, `CF_ZONE_ID` from Cloudflare dashboard
- `CF_DOMAIN` = your actual domain
- `CF_SUBDOMAIN` = `tychos`
- `CF_ACCESS_EMAIL` = `user@example.com`
- `TYCHOS_DIR` = `/Users/adam/Projects/tychos`
- `TYCHOS_PORT` = `8000`

- [ ] **Step 2: Run setup**

```bash
cd /Users/adam/Projects/tychos
./local_deploy/setup.sh
```

Verify output shows all 9 steps passing.

- [ ] **Step 3: Verify services are running**

```bash
# Check launchd services
launchctl print gui/$(id -u)/com.tychos.server
launchctl print gui/$(id -u)/com.tychos.worker

# Check processes
ps aux | grep -E '(uvicorn|server\.worker)' | grep -v grep

# Check local access
curl -s http://localhost:8000/api/dashboard | head -c 200
curl -s http://localhost:8000/runs | head -c 200
```

Expected: Both services running, API returns JSON, `/runs` returns SPA HTML.

- [ ] **Step 4: Verify tunnel access**

Open `https://tychos.yourdomain.com` in a browser. Cloudflare Access should prompt for email verification. After verifying with `user@example.com`, the Tychos admin UI should load.

- [ ] **Step 5: Check logs**

```bash
tail -20 logs/server.log
tail -20 logs/worker.log
```

Verify uvicorn startup messages and worker poll messages appear.

- [ ] **Step 6: Test crash recovery**

```bash
# Kill the server process
kill $(pgrep -f "uvicorn server.app")

# Wait a few seconds, then verify launchd restarted it
sleep 5
curl -s http://localhost:8000/api/dashboard | head -c 100
```

Expected: Server comes back automatically.
