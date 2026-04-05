ALTER TABLE eclipse_results ADD COLUMN moon_ra_vel REAL;
ALTER TABLE eclipse_results ADD COLUMN moon_dec_vel REAL;

ALTER TABLE jpl_reference ADD COLUMN moon_ra_vel REAL;
ALTER TABLE jpl_reference ADD COLUMN moon_dec_vel REAL;
