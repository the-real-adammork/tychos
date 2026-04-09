-- JPL positions at JPL's own best_jd (for overlay diagram)
ALTER TABLE jpl_reference ADD COLUMN sun_ra_at_best_rad REAL;
ALTER TABLE jpl_reference ADD COLUMN sun_dec_at_best_rad REAL;
ALTER TABLE jpl_reference ADD COLUMN moon_ra_at_best_rad REAL;
ALTER TABLE jpl_reference ADD COLUMN moon_dec_at_best_rad REAL;

-- Tychos positions at JPL's best_jd (scanner already computes, now persisted)
ALTER TABLE eclipse_results ADD COLUMN tychos_sun_ra_at_jpl_rad REAL;
ALTER TABLE eclipse_results ADD COLUMN tychos_sun_dec_at_jpl_rad REAL;
ALTER TABLE eclipse_results ADD COLUMN tychos_moon_ra_at_jpl_rad REAL;
ALTER TABLE eclipse_results ADD COLUMN tychos_moon_dec_at_jpl_rad REAL;
