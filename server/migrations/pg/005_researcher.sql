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

CREATE TABLE research_messages (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    research_job_id INTEGER NOT NULL REFERENCES research_jobs(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    consumed BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TEXT NOT NULL DEFAULT (to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS'))
);

CREATE INDEX idx_research_messages_job ON research_messages(research_job_id, consumed);

ALTER TABLE research_jobs ADD COLUMN model TEXT NOT NULL DEFAULT 'claude-sonnet-4-6';
ALTER TABLE research_jobs ADD COLUMN max_iterations INTEGER NOT NULL DEFAULT 40;
ALTER TABLE research_jobs ADD COLUMN max_wall_clock_seconds INTEGER NOT NULL DEFAULT 3600;
ALTER TABLE research_jobs ADD COLUMN no_improvement_plateau INTEGER NOT NULL DEFAULT 6;
ALTER TABLE research_jobs ADD COLUMN current_iteration INTEGER NOT NULL DEFAULT 0;
ALTER TABLE research_jobs ADD COLUMN iterations_since_checkpoint INTEGER NOT NULL DEFAULT 0;
ALTER TABLE research_jobs ADD COLUMN session_started_at TEXT;

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
