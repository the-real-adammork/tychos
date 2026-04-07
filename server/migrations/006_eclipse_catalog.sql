-- NASA Five Millennium Canon eclipse catalog data (solar + lunar)
CREATE TABLE IF NOT EXISTS eclipse_catalog (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    test_type TEXT NOT NULL,  -- 'solar' or 'lunar'
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

    -- Solar-specific
    qle TEXT,
    lat INTEGER,
    lon INTEGER,
    sun_alt_deg INTEGER,
    path_width_km INTEGER,
    duration_s INTEGER,

    -- Lunar-specific
    qse TEXT,
    pen_mag REAL,
    um_mag REAL,
    pen_duration_min REAL,
    par_duration_min REAL,
    total_duration_min REAL,
    zenith_lat INTEGER,
    zenith_lon INTEGER
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_eclipse_catalog_type_jd
    ON eclipse_catalog(test_type, julian_day_tt);

CREATE INDEX IF NOT EXISTS idx_eclipse_catalog_type
    ON eclipse_catalog(test_type, type);
