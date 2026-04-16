#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."

set -a
source local_deploy/.env
set +a
source tychos_skyfield/.venv/bin/activate

export DATABASE_URL=postgres://tychos:tychos@localhost:5432/tychos_research_redesign
export TYCHOS_ADMIN_USER=admin@t.local
export TYCHOS_ADMIN_PASSWORD=pw
export PYTHONPATH=tychos_skyfield:tests:.

echo "=== Resetting dev DB ==="
psql "$DATABASE_URL" -c "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;" 2>/dev/null

echo "=== Running init_db ==="
python -c "from server.db import init_db; init_db()"

echo "=== Starting smoke test (2 iterations, 1950-1952 date range) ==="
python -c "
import asyncio, json
from server.db import get_db, get_async_db

with get_db() as conn:
    with conn.cursor() as cur:
        cur.execute(\"DELETE FROM runs WHERE status='queued'\")
    conn.commit()

from server.worker import start_worker
start_worker()

async def go():
    async with get_async_db() as conn:
        job_id = await conn.fetchval(
            \"INSERT INTO research_jobs (name, param_set_id, dataset_id, view_name, allowlist, status, max_iterations, date_start, date_end) \"
            \"VALUES ('smoke', 1, 1, 'v_solar_position', '{sun.*}', 'active', 2, '1950-01-01', '1952-12-31') RETURNING id\"
        )
    print(f'Job {job_id} created, starting session...')
    from server.researcher.session import run_research_session
    await run_research_session(job_id)
    async with get_async_db() as conn:
        job = await conn.fetchrow('SELECT status, current_iteration FROM research_jobs WHERE id=\$1', job_id)
        logs = await conn.fetch('SELECT role, tool_name, content FROM research_logs WHERE research_job_id=\$1 ORDER BY id', job_id)
        iters = await conn.fetch('SELECT kind, objective FROM research_iterations WHERE research_job_id=\$1 ORDER BY id', job_id)
    print()
    print(f'=== Result: status={job[\"status\"]}, iterations={job[\"current_iteration\"]} ===')
    print(f'Log entries: {len(logs)}')
    print()
    for l in logs:
        content = (l['content'] or '')[:120]
        print(f'  {l[\"role\"]:12s} {l[\"tool_name\"] or \"\": <20s} {content}')
    print()
    print(f'Iterations logged: {len(iters)}')
    for it in iters:
        print(f'  {it[\"kind\"]:16s} objective={it[\"objective\"]}')

asyncio.run(go())
"
