#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TYCHOS_DIR="$(dirname "$SCRIPT_DIR")"

# Rebuild SPA if admin/ has changes
echo "Building admin SPA..."
cd "${TYCHOS_DIR}/admin"
npm run build --silent
cd "${TYCHOS_DIR}"

echo "Restarting services..."
launchctl kickstart -k "gui/$(id -u)/com.tychos.server"
launchctl kickstart -k "gui/$(id -u)/com.tychos.worker"

echo "Done. Logs: tail -f ${TYCHOS_DIR}/logs/server.log"
