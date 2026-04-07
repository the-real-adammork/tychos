-- Store the JPL minimum-separation time so we can report
-- (a) JPL's own timing offset vs the NASA catalog time and
-- (b) the offset between the Tychos and JPL minima.
ALTER TABLE jpl_reference ADD COLUMN best_jd REAL;
ALTER TABLE eclipse_results ADD COLUMN jpl_timing_offset_min REAL;
