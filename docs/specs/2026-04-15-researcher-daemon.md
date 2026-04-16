# Researcher Daemon

## Summary

An autonomous research agent that runs inside the FastAPI server as async tasks, driving Claude Agent SDK conversations to iteratively optimize Tychos orbital parameters. Each active research job gets one async task. Claude has tools to propose params, checkpoint winners, restore from checkpoints, and trigger Nelder-Mead searches. Users can pause the agent, inject guidance messages, and resume — all through API endpoints that the admin UI will later consume.

## Goals

- Autonomous parameter optimization via Claude Agent SDK (API-key-funded)
- One async task per active research job, managed by the server lifespan
- Budget enforcement: max iterations (40), wall-clock (1hr), no-improvement plateau (6)
- Pause + inject: user stops the agent, adds messages to the conversation, resumes
- Full conversation logging for replay, streaming, and debugging
- Crash recovery: active jobs auto-resume on server restart

## Non-Goals (Phase 2)

- Admin UI (separate spec — built on top of these endpoints)
- Multi-user API key management (single `ANTHROPIC_API_KEY` env var)
- Live WebSocket streaming to the browser (SSE endpoint is included; WebSocket is Phase 3)

---

## Architecture

```
FastAPI Server Process
  ├── API Routes (existing + new research control endpoints)
  ├── Researcher Tasks (one asyncio.Task per active job)
  │     ├── Claude Agent SDK session (model configurable per job)
  │     ├── Tools: propose_params, checkpoint, restore, search
  │     ├── Between turns: check budget, check user messages, log events
  │     └── Communicates with worker via existing run queue + NOTIFY
  └── Lifespan: on startup, resume any status='active' jobs

Worker Process (unchanged)
  └── Processes queued runs via LISTEN/NOTIFY as before
```

No new processes. The researcher is I/O-bound (SDK calls, API calls, waiting for worker NOTIFY) — ideal for asyncio tasks inside the server.

---

## Database Changes

### New Table: `research_logs`

```sql
CREATE TABLE research_logs (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    research_job_id INTEGER NOT NULL REFERENCES research_jobs(id) ON DELETE CASCADE,
    research_iteration_id INTEGER REFERENCES research_iterations(id),
    role TEXT NOT NULL,
    content TEXT,
    tool_name TEXT,
    token_count INTEGER,
    created_at TEXT NOT NULL DEFAULT (to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS'))
);

CREATE INDEX idx_research_logs_job ON research_logs(research_job_id, created_at);
```

`role` values: `'assistant'`, `'tool_call'`, `'tool_result'`, `'user_inject'`, `'system'`.

### New Table: `research_messages`

```sql
CREATE TABLE research_messages (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    research_job_id INTEGER NOT NULL REFERENCES research_jobs(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    consumed BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TEXT NOT NULL DEFAULT (to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS'))
);

CREATE INDEX idx_research_messages_job ON research_messages(research_job_id, consumed);
```

### Modified Table: `research_jobs`

```sql
ALTER TABLE research_jobs ADD COLUMN model TEXT NOT NULL DEFAULT 'claude-sonnet-4-6';
ALTER TABLE research_jobs ADD COLUMN max_iterations INTEGER NOT NULL DEFAULT 40;
ALTER TABLE research_jobs ADD COLUMN max_wall_clock_seconds INTEGER NOT NULL DEFAULT 3600;
ALTER TABLE research_jobs ADD COLUMN no_improvement_plateau INTEGER NOT NULL DEFAULT 6;
ALTER TABLE research_jobs ADD COLUMN current_iteration INTEGER NOT NULL DEFAULT 0;
ALTER TABLE research_jobs ADD COLUMN iterations_since_checkpoint INTEGER NOT NULL DEFAULT 0;
ALTER TABLE research_jobs ADD COLUMN session_started_at TEXT;
```

### New NOTIFY Trigger

```sql
CREATE OR REPLACE FUNCTION notify_research_log_append() RETURNS trigger AS $$
BEGIN
    PERFORM pg_notify('research_log_append',
        json_build_object('job_id', NEW.research_job_id, 'log_id', NEW.id, 'role', NEW.role)::text);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_research_log_append
    AFTER INSERT ON research_logs
    FOR EACH ROW EXECUTE FUNCTION notify_research_log_append();
```

---

## API Endpoints

### New Endpoints

```
POST   /api/research/{id}/start         -- set status='active', spawn async task
POST   /api/research/{id}/pause         -- set status='paused', task stops after current turn
POST   /api/research/{id}/resume        -- set status='active', respawn task from research_logs
POST   /api/research/{id}/message       -- write to research_messages (injected next turn)
GET    /api/research/{id}/logs          -- paginated research_logs (chat UI data)
GET    /api/research/{id}/logs/stream   -- SSE bridging NOTIFY research_log_append
```

### Modified `POST /api/research` (create job)

Accepts new optional fields with defaults:

```json
{
    "model": "claude-sonnet-4-6",
    "max_iterations": 40,
    "max_wall_clock_seconds": 3600,
    "no_improvement_plateau": 6
}
```

Job is created with `status='pending'`. Requires explicit `POST .../start` to begin.

---

## SDK Session & Tools

### System Prompt

The job's `instructions` field (already rendered at creation — contains Tychos model background, allowlist, view, date range, and strategy guidance).

### Initial User Message (fresh start)

Current state snapshot:
- Latest checkpoint params (or v1 if none)
- Last N iteration objectives (from `research_iterations`)
- Most recent view detail (full if resuming from checkpoint, abbreviated otherwise)

### Tools

| Tool | Parameters | Behavior | Returns |
|---|---|---|---|
| `propose_params` | `params_json: str` | Validates allowlist, creates version, waits for worker run via NOTIFY, reads view | `{objective, n_scored, detail, version_id, run_id}` |
| `checkpoint` | `version_id: int` | Marks version as checkpoint, resets plateau counter | `{ok: true}` |
| `restore` | `version_id: int` | Creates new version from checkpoint params, waits for run | `{objective, n_scored, detail, version_id, run_id}` |
| `search` | `param_keys: list[str], budget: int, scale: float` | Triggers server-side Nelder-Mead | `{starting_objective, best_objective, improved, n_evals, winner_version_id}` |

### Detail Truncation

- **Normal iterations** (`propose_params`): return top 10 worst eclipses in `detail`.
- **Decision points** (after `checkpoint`, `restore`, or `search` with `improved=true`): return **full** view detail (all `n_scored` rows).

### Budget Accounting

- Each `propose_params` call = 1 iteration.
- Each `search` call = 1 iteration (regardless of internal eval count).
- `checkpoint` and `restore` do not count toward iteration budget.

---

## Researcher Task Lifecycle

```
run_research_session(job_id):
  1. Load job config (instructions, allowlist, view, model, budgets)
  2. Build initial context:
     - If resuming: reconstruct conversation from research_logs
     - If fresh: system prompt = instructions, user msg = current state snapshot
  3. Create Anthropic SDK client with job's model + ANTHROPIC_API_KEY
  4. Define tools (propose_params, checkpoint, restore, search)
  5. Loop:
     a. Send conversation to SDK → get response (streamed)
     b. For each event in stream:
        - Log to research_logs + fires NOTIFY via trigger
        - If tool_call: execute tool, log result, update counters
     c. After Claude yields:
        - Check budget:
          - current_iteration >= max_iterations → pause
          - wall-clock elapsed >= max_wall_clock_seconds → pause
          - iterations_since_checkpoint >= no_improvement_plateau → pause
        - Check research_messages (consumed=FALSE):
          - If any: inject as user messages, mark consumed, continue
        - Check job status (re-read from DB):
          - If 'paused' (user clicked pause): return
     d. Continue loop with updated conversation
  6. On budget hit: log 'budget_exhausted' to research_logs, set status='paused'
  7. On error: log error, retry up to 3 times (30s backoff), then pause with kind='error'
```

### Crash Recovery

On server startup (lifespan handler):
1. Query `research_jobs WHERE status='active'`
2. For each: spawn `run_research_session(job_id)`
3. Session reconstructs conversation from `research_logs` and continues

State lives entirely in the DB. No in-memory state survives a restart.

### Pause + Resume Flow

1. User calls `POST /api/research/{id}/pause`
2. API sets `status='paused'` in DB
3. Researcher task sees `status='paused'` at next budget check → returns
4. User (optionally) calls `POST /api/research/{id}/message` to inject guidance
5. User calls `POST /api/research/{id}/resume`
6. API sets `status='active'`, spawns new async task
7. Task reconstructs conversation from `research_logs`, appends any unconsumed `research_messages`, continues SDK session

---

## Configuration

### Environment Variables

```
ANTHROPIC_API_KEY=sk-ant-...    # Required for researcher daemon
```

Added to `start-server.sh` guard and `local_deploy/.env.example`.

### Per-Job Overrides

All budget fields and model are configurable per job at creation or via PATCH:

```json
PATCH /api/research/{id}
{
    "model": "claude-opus-4-6",
    "max_iterations": 80,
    "max_wall_clock_seconds": 7200,
    "no_improvement_plateau": 12
}
```

---

## Testing Strategy

- **Unit: tool execution** — mock SDK, verify `propose_params` calls the right API sequence, waits for NOTIFY, returns correct shape
- **Unit: budget enforcement** — verify each limit (iterations, wall-clock, plateau) triggers pause at the right threshold
- **Unit: message injection** — verify unconsumed messages get injected between turns and marked consumed
- **Unit: conversation reconstruction** — verify `research_logs` rows rebuild a valid SDK conversation
- **Integration: full session** — create job, start, let SDK make 2-3 tool calls with a mock Claude that proposes known params, verify iterations logged and view results correct
- **Integration: pause/inject/resume** — start session, pause mid-run, inject message, resume, verify message appears in conversation
- **Integration: crash recovery** — start session, kill server, restart, verify session resumes from logs
- **Smoke: real SDK** — single iteration with real `ANTHROPIC_API_KEY` against the test DB, verify end-to-end (expensive, run manually)

---

## Dependencies

- `anthropic` Python SDK (add to `requirements.txt`)
- `ANTHROPIC_API_KEY` env var

---

## What Gets Modified

- `server/app.py` — lifespan adds crash-recovery scan; register new endpoints
- `server/api/research_routes.py` — new control endpoints (start/pause/resume/message/logs/stream)
- `requirements.txt` — add `anthropic`

## What Gets Created

- `server/migrations/pg/005_researcher.sql` — new tables + altered columns + trigger
- `server/researcher.py` — async task runner, tool definitions, budget enforcement, conversation management
- `tests/test_researcher.py` — unit + integration tests
- `tests/test_researcher_e2e.py` — full session test with mocked SDK
