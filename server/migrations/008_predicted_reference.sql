CREATE TABLE IF NOT EXISTS predicted_reference (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    julian_day_tt REAL NOT NULL,
    test_type TEXT NOT NULL,
    expected_separation_arcmin REAL NOT NULL,
    moon_apparent_radius_arcmin REAL NOT NULL,
    sun_apparent_radius_arcmin REAL,
    umbra_radius_arcmin REAL,
    penumbra_radius_arcmin REAL,
    approach_angle_deg REAL,
    gamma REAL NOT NULL,
    catalog_magnitude REAL NOT NULL,
    UNIQUE(julian_day_tt, test_type)
);

ALTER TABLE eclipse_results ADD COLUMN tychos_error_arcmin REAL;
ALTER TABLE eclipse_results ADD COLUMN jpl_error_arcmin REAL;
