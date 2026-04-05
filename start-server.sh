#!/bin/bash
cd "$(dirname "$0")"
source tychos_skyfield/.venv/bin/activate
PYTHONPATH=tychos_skyfield:tests:. exec uvicorn server.app:app --port 8000 --reload
