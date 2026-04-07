#!/bin/bash
set -euo pipefail

# ── Load config ───────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env"

if [ ! -f "$ENV_FILE" ]; then
    echo "ERROR: ${ENV_FILE} not found. Copy .env.example to .env and fill in values."
    exit 1
fi

source "$ENV_FILE"

# Validate required vars
for var in CF_API_TOKEN CF_ACCOUNT_ID CF_ZONE_ID CF_DOMAIN CF_SUBDOMAIN CF_ACCESS_EMAILS TYCHOS_DIR TYCHOS_PORT; do
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

# ── Check prerequisites ──────────────────────────────────────
echo "[1/9] Checking prerequisites..."
for cmd in python3 node npm cloudflared jq; do
    if ! command -v "$cmd" &>/dev/null; then
        echo "ERROR: $cmd not found. Install it first."
        exit 1
    fi
done
# OpenBLAS is required to build scipy from source (needed on Python 3.14+)
if ! pkg-config --exists openblas 2>/dev/null; then
    echo "ERROR: openblas not found. Install it with: brew install openblas"
    exit 1
fi
echo "  All prerequisites found."

# ── Python environment ───────────────────────────────────────
echo "[2/9] Setting up Python environment..."
VENV_DIR="${TYCHOS_DIR}/tychos_skyfield/.venv"
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
fi
source "${VENV_DIR}/bin/activate"
# Ensure pip can find OpenBLAS (Homebrew doesn't link it by default)
export PKG_CONFIG_PATH="$(brew --prefix openblas)/lib/pkgconfig${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}"
# Install server deps (pure Python, always fast)
pip install -q -r "${TYCHOS_DIR}/server/requirements.txt"
# For scientific deps, skip if already importable (avoids building scipy from source on Python 3.14)
python3 -c "import numpy, scipy, skyfield" 2>/dev/null || pip install -q -r "${TYCHOS_DIR}/tychos_skyfield/requirements.txt"
python3 -c "import pytest" 2>/dev/null || pip install -q -r "${TYCHOS_DIR}/requirements.txt"
echo "  Python deps installed."

# ── Build admin SPA ──────────────────────────────────────────
echo "[3/9] Building admin SPA..."
cd "${TYCHOS_DIR}/admin"
npm install --silent
npm run build
cd "${TYCHOS_DIR}"
echo "  SPA built to admin/dist/."

# ── Initialize database ─────────────────────────────────────
echo "[4/9] Initializing database..."
cd "${TYCHOS_DIR}"
PYTHONPATH=tychos_skyfield:tests:. python3 -c "from server.db import init_db; init_db()"
echo "  Database ready."

# ── Create logs directory ────────────────────────────────────
mkdir -p "$LOGS_DIR"

# ── Verify CF token ──────────────────────────────────────────
echo "[5/9] Verifying Cloudflare API token..."
VERIFY_RESP=$(curl -s "${CF_API}/accounts/${CF_ACCOUNT_ID}/tokens/verify" \
    -H "Authorization: Bearer ${CF_API_TOKEN}")
if [ "$(echo "$VERIFY_RESP" | jq -r '.success')" != "true" ]; then
    echo "ERROR: Cloudflare API token verification failed."
    echo "$VERIFY_RESP" | jq '.errors'
    exit 1
fi
echo "  Token valid."

# ── Detect existing tunnel ───────────────────────────────────
echo "[6/9] Detecting existing Cloudflare Tunnel..."
CF_DAEMON_PLIST="/Library/LaunchDaemons/com.cloudflare.cloudflared.plist"

if [ -f "$CF_DAEMON_PLIST" ]; then
    # cloudflared is already installed — extract tunnel ID from its token
    CF_TOKEN=$(defaults read "${CF_DAEMON_PLIST%.plist}" ProgramArguments 2>/dev/null \
        | grep -oE '[A-Za-z0-9+/=]{50,}' | head -1)
    if [ -n "$CF_TOKEN" ]; then
        TUNNEL_ID=$(echo "$CF_TOKEN" | base64 -d 2>/dev/null | jq -r '.t // empty')
    fi

    if [ -z "${TUNNEL_ID:-}" ]; then
        echo "ERROR: cloudflared is installed but could not extract tunnel ID from its token."
        exit 1
    fi

    TUNNEL_NAME=$(curl -s "${CF_API}/accounts/${CF_ACCOUNT_ID}/cfd_tunnel/${TUNNEL_ID}" \
        -H "Authorization: Bearer ${CF_API_TOKEN}" | jq -r '.result.name // empty')
    echo "  Using existing tunnel: ${TUNNEL_NAME} (${TUNNEL_ID})"
else
    # No cloudflared service — create a new tunnel and install it
    echo "  No cloudflared service found. Creating tunnel..."
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
fi

# ── Add ingress hostname ─────────────────────────────────────
echo "[7/9] Adding ingress hostname for ${HOSTNAME}..."

# Get current tunnel config to preserve existing ingress rules
CURRENT_CONFIG=$(curl -s "${CF_API}/accounts/${CF_ACCOUNT_ID}/cfd_tunnel/${TUNNEL_ID}/configurations" \
    -H "Authorization: Bearer ${CF_API_TOKEN}")

# Build new ingress: existing rules (minus catch-all) + tychos rule + catch-all
# Remove any existing rule for our hostname to make this idempotent
EXISTING_RULES=$(echo "$CURRENT_CONFIG" | jq -r '[.result.config.ingress[] | select(.hostname != null and .hostname != "'"${HOSTNAME}"'")]')
TYCHOS_RULE="{\"hostname\":\"${HOSTNAME}\",\"service\":\"http://127.0.0.1:${TYCHOS_PORT}\"}"
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

# ── Create DNS CNAME ─────────────────────────────────────────
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

# Build email include rules from comma-separated CF_ACCESS_EMAILS (jq-based)
EMAIL_INCLUDES=$(echo "$CF_ACCESS_EMAILS" | tr ',' '\n' | jq -R '{email:{email:.}}' | jq -s '.')
POLICY_PAYLOAD=$(jq -n --argjson includes "$EMAIL_INCLUDES" \
    '{name:"Allow owners",decision:"allow",include:$includes}')

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

    curl -s -X POST \
        "${CF_API}/accounts/${CF_ACCOUNT_ID}/access/apps/${APP_ID}/policies" \
        -H "Authorization: Bearer ${CF_API_TOKEN}" \
        -H "Content-Type: application/json" \
        --data "$POLICY_PAYLOAD" > /dev/null
    echo "  Access app and policy created."
else
    echo "  Access app already exists. Updating access policy..."

    # Find existing policy ID
    POLICIES_RESP=$(curl -s "${CF_API}/accounts/${CF_ACCOUNT_ID}/access/apps/${APP_ID}/policies" \
        -H "Authorization: Bearer ${CF_API_TOKEN}")
    POLICY_ID=$(echo "$POLICIES_RESP" | jq -r '.result[0].id // empty')

    if [ -n "$POLICY_ID" ]; then
        curl -s -X PUT \
            "${CF_API}/accounts/${CF_ACCOUNT_ID}/access/apps/${APP_ID}/policies/${POLICY_ID}" \
            -H "Authorization: Bearer ${CF_API_TOKEN}" \
            -H "Content-Type: application/json" \
            --data "$POLICY_PAYLOAD" > /dev/null
        echo "  Access policy updated."
    else
        curl -s -X POST \
            "${CF_API}/accounts/${CF_ACCOUNT_ID}/access/apps/${APP_ID}/policies" \
            -H "Authorization: Bearer ${CF_API_TOKEN}" \
            -H "Content-Type: application/json" \
            --data "$POLICY_PAYLOAD" > /dev/null
        echo "  Access policy created."
    fi
fi

# ── Install launchd plists ───────────────────────────────────
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
