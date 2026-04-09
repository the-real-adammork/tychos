#!/bin/bash
# Wrapper to run the research CLI with the correct Python + paths
cd "$(dirname "$0")"
PYTHONPATH=tychos_skyfield:tests exec ./tychos_skyfield/.venv/bin/python3 -m server.research "$@"
