#!/bin/bash
cd "$(dirname "$0")"
source tychos_skyfield/.venv/bin/activate
PYTHONPATH=tychos_skyfield:tests:. exec python -m server.worker
