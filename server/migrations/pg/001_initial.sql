CREATE TABLE users (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS'))
);

CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at TEXT NOT NULL
);

CREATE TABLE datasets (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    event_type TEXT NOT NULL,
    source_url TEXT,
    description TEXT,
    record_count INTEGER NOT NULL DEFAULT 0,
    scan_window_hours DOUBLE PRECISION NOT NULL DEFAULT 6.0,
    created_at TEXT NOT NULL DEFAULT (to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS'))
);

INSERT INTO datasets (slug, name, event_type, source_url, description) VALUES
    ('solar_eclipse', 'NASA Solar Eclipses', 'solar_eclipse',
     'https://eclipse.gsfc.nasa.gov/SEcat5/',
     'Five Millennium Canon of Solar Eclipses (1901-2100)'),
    ('lunar_eclipse', 'NASA Lunar Eclipses', 'lunar_eclipse',
     'https://eclipse.gsfc.nasa.gov/LEcat5/',
     'Five Millennium Canon of Lunar Eclipses (1901-2100)');

CREATE TABLE param_sets (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    forked_from_id INTEGER REFERENCES param_sets(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT (to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS'))
);

CREATE TABLE param_versions (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    param_set_id INTEGER NOT NULL REFERENCES param_sets(id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL DEFAULT 1,
    parent_version_id INTEGER REFERENCES param_versions(id) ON DELETE SET NULL,
    params_md5 TEXT NOT NULL,
    params_json TEXT NOT NULL,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS'))
);

CREATE TABLE runs (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    param_version_id INTEGER NOT NULL REFERENCES param_versions(id) ON DELETE CASCADE,
    dataset_id INTEGER NOT NULL REFERENCES datasets(id),
    status TEXT NOT NULL DEFAULT 'queued',
    code_version TEXT NOT NULL DEFAULT '1.0',
    tsn_commit TEXT,
    skyfield_commit TEXT,
    total_eclipses INTEGER,
    detected INTEGER,
    mean_sun_diff DOUBLE PRECISION,
    mean_moon_diff DOUBLE PRECISION,
    mean_timing_offset DOUBLE PRECISION,
    created_at TEXT NOT NULL DEFAULT (to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS')),
    started_at TEXT,
    completed_at TEXT,
    error TEXT
);

CREATE INDEX idx_runs_status_created ON runs(status, created_at);

CREATE TABLE eclipse_catalog (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    dataset_id INTEGER NOT NULL REFERENCES datasets(id),
    catalog_number TEXT NOT NULL,
    julian_day_tt DOUBLE PRECISION NOT NULL,
    date TEXT NOT NULL,
    delta_t_s INTEGER,
    luna_num INTEGER,
    saros_num INTEGER,
    type_raw TEXT NOT NULL,
    type TEXT NOT NULL,
    gamma DOUBLE PRECISION,
    magnitude DOUBLE PRECISION NOT NULL,
    qle TEXT,
    lat INTEGER,
    lon INTEGER,
    sun_alt_deg INTEGER,
    path_width_km INTEGER,
    duration_s INTEGER,
    qse TEXT,
    pen_mag DOUBLE PRECISION,
    um_mag DOUBLE PRECISION,
    pen_duration_min DOUBLE PRECISION,
    par_duration_min DOUBLE PRECISION,
    total_duration_min DOUBLE PRECISION,
    zenith_lat INTEGER,
    zenith_lon INTEGER
);
CREATE UNIQUE INDEX idx_eclipse_catalog_dataset_jd ON eclipse_catalog(dataset_id, julian_day_tt);
CREATE INDEX idx_eclipse_catalog_dataset_type ON eclipse_catalog(dataset_id, type);

CREATE TABLE jpl_reference (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    dataset_id INTEGER NOT NULL REFERENCES datasets(id),
    julian_day_tt DOUBLE PRECISION NOT NULL,
    sun_ra_rad DOUBLE PRECISION NOT NULL,
    sun_dec_rad DOUBLE PRECISION NOT NULL,
    moon_ra_rad DOUBLE PRECISION NOT NULL,
    moon_dec_rad DOUBLE PRECISION NOT NULL,
    separation_arcmin DOUBLE PRECISION NOT NULL,
    moon_ra_vel DOUBLE PRECISION,
    moon_dec_vel DOUBLE PRECISION,
    best_jd DOUBLE PRECISION,
    sun_ra_at_best_rad DOUBLE PRECISION,
    sun_dec_at_best_rad DOUBLE PRECISION,
    moon_ra_at_best_rad DOUBLE PRECISION,
    moon_dec_at_best_rad DOUBLE PRECISION
);
CREATE UNIQUE INDEX idx_jpl_reference_dataset_jd ON jpl_reference(dataset_id, julian_day_tt);

CREATE TABLE predicted_reference (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    julian_day_tt DOUBLE PRECISION NOT NULL,
    test_type TEXT NOT NULL,
    expected_separation_arcmin DOUBLE PRECISION NOT NULL,
    moon_apparent_radius_arcmin DOUBLE PRECISION NOT NULL,
    sun_apparent_radius_arcmin DOUBLE PRECISION,
    umbra_radius_arcmin DOUBLE PRECISION,
    penumbra_radius_arcmin DOUBLE PRECISION,
    approach_angle_deg DOUBLE PRECISION,
    gamma DOUBLE PRECISION NOT NULL,
    catalog_magnitude DOUBLE PRECISION NOT NULL,
    UNIQUE(julian_day_tt, test_type)
);

CREATE TABLE eclipse_results (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    julian_day_tt DOUBLE PRECISION NOT NULL,
    date TEXT NOT NULL,
    catalog_type TEXT NOT NULL,
    magnitude DOUBLE PRECISION NOT NULL,
    detected BOOLEAN NOT NULL,
    threshold_arcmin DOUBLE PRECISION NOT NULL,
    min_separation_arcmin DOUBLE PRECISION,
    timing_offset_min DOUBLE PRECISION,
    best_jd DOUBLE PRECISION,
    sun_ra_rad DOUBLE PRECISION,
    sun_dec_rad DOUBLE PRECISION,
    moon_ra_rad DOUBLE PRECISION,
    moon_dec_rad DOUBLE PRECISION,
    moon_error_arcmin DOUBLE PRECISION,
    moon_ra_vel DOUBLE PRECISION,
    moon_dec_vel DOUBLE PRECISION,
    tychos_error_arcmin DOUBLE PRECISION,
    jpl_error_arcmin DOUBLE PRECISION,
    jpl_timing_offset_min DOUBLE PRECISION,
    sun_delta_ra_arcmin DOUBLE PRECISION,
    sun_delta_dec_arcmin DOUBLE PRECISION,
    moon_delta_ra_arcmin DOUBLE PRECISION,
    moon_delta_dec_arcmin DOUBLE PRECISION,
    tychos_sun_ra_at_jpl_rad DOUBLE PRECISION,
    tychos_sun_dec_at_jpl_rad DOUBLE PRECISION,
    tychos_moon_ra_at_jpl_rad DOUBLE PRECISION,
    tychos_moon_dec_at_jpl_rad DOUBLE PRECISION
);

CREATE INDEX idx_eclipse_results_run ON eclipse_results(run_id);
CREATE INDEX idx_eclipse_results_run_date ON eclipse_results(run_id, date);
