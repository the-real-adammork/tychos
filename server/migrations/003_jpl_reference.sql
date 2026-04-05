CREATE TABLE IF NOT EXISTS jpl_reference (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    julian_day_tt REAL NOT NULL UNIQUE,
    test_type TEXT NOT NULL,
    sun_ra_rad REAL NOT NULL,
    sun_dec_rad REAL NOT NULL,
    moon_ra_rad REAL NOT NULL,
    moon_dec_rad REAL NOT NULL,
    separation_arcmin REAL NOT NULL
);
