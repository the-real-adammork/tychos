#!/bin/bash
cd "$(dirname "$0")"
source tychos_skyfield/.venv/bin/activate
: "${DATABASE_URL:?DATABASE_URL not set (e.g. postgres://tychos:tychos@localhost:5432/tychos)}"
PYTHONPATH=tychos_skyfield:tests:. exec uvicorn server.app:app --port 8000 --reload
