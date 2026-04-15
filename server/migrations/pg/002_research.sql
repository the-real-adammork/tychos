ALTER TABLE param_versions
    ADD COLUMN is_checkpoint BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE runs ADD COLUMN date_start TEXT;
ALTER TABLE runs ADD COLUMN date_end TEXT;

CREATE TABLE research_jobs (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL,
    param_set_id INTEGER NOT NULL REFERENCES param_sets(id),
    dataset_id INTEGER NOT NULL REFERENCES datasets(id),
    view_name TEXT NOT NULL,
    allowlist TEXT[] NOT NULL,
    date_start TEXT,
    date_end TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    instructions TEXT,
    created_at TEXT NOT NULL DEFAULT (to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS')),
    updated_at TEXT
);

CREATE INDEX idx_research_jobs_status ON research_jobs(status);

CREATE TABLE research_iterations (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    research_job_id INTEGER NOT NULL REFERENCES research_jobs(id) ON DELETE CASCADE,
    param_version_id INTEGER NOT NULL REFERENCES param_versions(id),
    run_id INTEGER REFERENCES runs(id),
    kind TEXT NOT NULL,
    objective DOUBLE PRECISION,
    aux_stats JSONB,
    created_at TEXT NOT NULL DEFAULT (to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS'))
);

CREATE INDEX idx_research_iterations_job ON research_iterations(research_job_id, created_at);
