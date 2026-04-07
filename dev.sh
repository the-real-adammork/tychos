#!/bin/bash
# Boot all services for local development.
# Usage: ./dev.sh
# Stop:  Ctrl-C (kills all three processes)

set -e
cd "$(dirname "$0")"

# Load environment variables from local_deploy/.env if present so dev runs
# share the same TYCHOS_ADMIN_USER / TYCHOS_ADMIN_PASSWORD as the deploy.
if [ -f local_deploy/.env ]; then
    set -a
    source local_deploy/.env
    set +a
fi

cleanup() {
    echo ""
    echo "Shutting down..."
    kill 0 2>/dev/null
    wait 2>/dev/null
}
trap cleanup EXIT INT TERM

echo "Starting API server  → http://localhost:8000"
echo "Starting admin UI    → http://localhost:5173"
echo "Starting worker"
echo "---"

# API server
source tychos_skyfield/.venv/bin/activate
PYTHONPATH=tychos_skyfield:tests:. uvicorn server.app:app --port 8000 --reload 2>&1 | sed 's/^/[server] /' &

# Worker
PYTHONPATH=tychos_skyfield:tests:. python -m server.worker 2>&1 | sed 's/^/[worker] /' &

# Admin dev server (runs npm from admin/)
(cd admin && npm run dev 2>&1 | sed 's/^/[admin]  /') &

wait
