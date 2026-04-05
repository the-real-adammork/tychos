CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at DATETIME NOT NULL
);

CREATE TABLE param_sets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    forked_from_id INTEGER REFERENCES param_sets(id) ON DELETE SET NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE param_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    param_set_id INTEGER NOT NULL REFERENCES param_sets(id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL DEFAULT 1,
    parent_version_id INTEGER REFERENCES param_versions(id) ON DELETE SET NULL,
    params_md5 TEXT NOT NULL,
    params_json TEXT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    param_version_id INTEGER NOT NULL REFERENCES param_versions(id) ON DELETE CASCADE,
    test_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    code_version TEXT NOT NULL DEFAULT '1.0',
    tsn_commit TEXT,
    skyfield_commit TEXT,
    total_eclipses INTEGER,
    detected INTEGER,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at DATETIME,
    completed_at DATETIME,
    error TEXT
);

CREATE TABLE eclipse_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    julian_day_tt REAL NOT NULL,
    date TEXT NOT NULL,
    catalog_type TEXT NOT NULL,
    magnitude REAL NOT NULL,
    detected BOOLEAN NOT NULL,
    threshold_arcmin REAL NOT NULL,
    min_separation_arcmin REAL,
    timing_offset_min REAL,
    best_jd REAL,
    sun_ra_rad REAL,
    sun_dec_rad REAL,
    moon_ra_rad REAL,
    moon_dec_rad REAL
);
