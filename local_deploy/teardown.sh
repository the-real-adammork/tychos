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

# ── Unload launchd services ──────────────────────────────────
echo "[1/4] Unloading launchd services..."
for label in com.tychos.server com.tychos.worker; do
    launchctl bootout "gui/$(id -u)/${label}" 2>/dev/null && echo "  Unloaded ${label}" || echo "  ${label} not loaded (skipped)"
    rm -f "${HOME}/Library/LaunchAgents/${label}.plist"
done

# ── Remove ingress hostname ──────────────────────────────────
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

# ── Delete DNS CNAME ─────────────────────────────────────────
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

# ── Delete Access app ────────────────────────────────────────
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
