-- 1. Create datasets table
CREATE TABLE datasets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    event_type TEXT NOT NULL,
    source_url TEXT,
    description TEXT,
    record_count INTEGER NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Seed the two initial datasets
INSERT INTO datasets (slug, name, event_type, source_url, description) VALUES
    ('solar_eclipse', 'NASA Solar Eclipses', 'solar_eclipse',
     'https://eclipse.gsfc.nasa.gov/SEcat5/',
     'Five Millennium Canon of Solar Eclipses (1901-2100)'),
    ('lunar_eclipse', 'NASA Lunar Eclipses', 'lunar_eclipse',
     'https://eclipse.gsfc.nasa.gov/LEcat5/',
     'Five Millennium Canon of Lunar Eclipses (1901-2100)');

-- 2. Recreate runs without test_type, with dataset_id FK
CREATE TABLE runs_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    param_version_id INTEGER NOT NULL REFERENCES param_versions(id) ON DELETE CASCADE,
    dataset_id INTEGER NOT NULL REFERENCES datasets(id),
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

INSERT INTO runs_new (id, param_version_id, dataset_id, status, code_version,
    tsn_commit, skyfield_commit, total_eclipses, detected,
    created_at, started_at, completed_at, error)
SELECT r.id, r.param_version_id,
    CASE r.test_type WHEN 'solar' THEN d_solar.id WHEN 'lunar' THEN d_lunar.id END,
    r.status, r.code_version, r.tsn_commit, r.skyfield_commit,
    r.total_eclipses, r.detected, r.created_at, r.started_at, r.completed_at, r.error
FROM runs r,
    (SELECT id FROM datasets WHERE slug = 'solar_eclipse') d_solar,
    (SELECT id FROM datasets WHERE slug = 'lunar_eclipse') d_lunar;

DROP TABLE runs;
ALTER TABLE runs_new RENAME TO runs;

-- 3. Recreate eclipse_catalog without test_type, with dataset_id FK
CREATE TABLE eclipse_catalog_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_id INTEGER NOT NULL REFERENCES datasets(id),
    catalog_number TEXT NOT NULL,
    julian_day_tt REAL NOT NULL,
    date TEXT NOT NULL,
    delta_t_s INTEGER,
    luna_num INTEGER,
    saros_num INTEGER,
    type_raw TEXT NOT NULL,
    type TEXT NOT NULL,
    gamma REAL,
    magnitude REAL NOT NULL,
    qle TEXT,
    lat INTEGER,
    lon INTEGER,
    sun_alt_deg INTEGER,
    path_width_km INTEGER,
    duration_s INTEGER,
    qse TEXT,
    pen_mag REAL,
    um_mag REAL,
    pen_duration_min REAL,
    par_duration_min REAL,
    total_duration_min REAL,
    zenith_lat INTEGER,
    zenith_lon INTEGER
);

INSERT INTO eclipse_catalog_new (id, dataset_id, catalog_number, julian_day_tt, date,
    delta_t_s, luna_num, saros_num, type_raw, type, gamma, magnitude,
    qle, lat, lon, sun_alt_deg, path_width_km, duration_s,
    qse, pen_mag, um_mag, pen_duration_min, par_duration_min,
    total_duration_min, zenith_lat, zenith_lon)
SELECT ec.id,
    CASE ec.test_type WHEN 'solar' THEN d_solar.id WHEN 'lunar' THEN d_lunar.id END,
    ec.catalog_number, ec.julian_day_tt, ec.date,
    ec.delta_t_s, ec.luna_num, ec.saros_num, ec.type_raw, ec.type,
    ec.gamma, ec.magnitude, ec.qle, ec.lat, ec.lon, ec.sun_alt_deg,
    ec.path_width_km, ec.duration_s, ec.qse, ec.pen_mag, ec.um_mag,
    ec.pen_duration_min, ec.par_duration_min, ec.total_duration_min,
    ec.zenith_lat, ec.zenith_lon
FROM eclipse_catalog ec,
    (SELECT id FROM datasets WHERE slug = 'solar_eclipse') d_solar,
    (SELECT id FROM datasets WHERE slug = 'lunar_eclipse') d_lunar;

DROP TABLE eclipse_catalog;
ALTER TABLE eclipse_catalog_new RENAME TO eclipse_catalog;

CREATE UNIQUE INDEX idx_eclipse_catalog_dataset_jd ON eclipse_catalog(dataset_id, julian_day_tt);
CREATE INDEX idx_eclipse_catalog_dataset_type ON eclipse_catalog(dataset_id, type);

-- 4. Recreate jpl_reference without test_type, with dataset_id FK
CREATE TABLE jpl_reference_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_id INTEGER NOT NULL REFERENCES datasets(id),
    julian_day_tt REAL NOT NULL,
    sun_ra_rad REAL NOT NULL,
    sun_dec_rad REAL NOT NULL,
    moon_ra_rad REAL NOT NULL,
    moon_dec_rad REAL NOT NULL,
    separation_arcmin REAL NOT NULL,
    moon_ra_vel REAL,
    moon_dec_vel REAL
);

INSERT INTO jpl_reference_new (id, dataset_id, julian_day_tt,
    sun_ra_rad, sun_dec_rad, moon_ra_rad, moon_dec_rad,
    separation_arcmin, moon_ra_vel, moon_dec_vel)
SELECT j.id,
    CASE j.test_type WHEN 'solar' THEN d_solar.id WHEN 'lunar' THEN d_lunar.id END,
    j.julian_day_tt, j.sun_ra_rad, j.sun_dec_rad, j.moon_ra_rad, j.moon_dec_rad,
    j.separation_arcmin, j.moon_ra_vel, j.moon_dec_vel
FROM jpl_reference j,
    (SELECT id FROM datasets WHERE slug = 'solar_eclipse') d_solar,
    (SELECT id FROM datasets WHERE slug = 'lunar_eclipse') d_lunar;

DROP TABLE jpl_reference;
ALTER TABLE jpl_reference_new RENAME TO jpl_reference;

CREATE UNIQUE INDEX idx_jpl_reference_dataset_jd ON jpl_reference(dataset_id, julian_day_tt);

-- 5. Update record_count on datasets
UPDATE datasets SET record_count = (
    SELECT COUNT(*) FROM eclipse_catalog WHERE dataset_id = datasets.id
);
