-- Add a per-dataset scan window (± hours around the catalog JD) used by the
-- scanner when searching for each eclipse's minimum separation.
--
-- The previous hard-coded 2.0 was small enough that tychos conjunctions which
-- fall outside ±2h pin to the window boundary, which makes timing_offset_min
-- saturate near ±136 min and hides real differences between parameter sets.
-- 6.0 hours gives plenty of headroom for the current v1 params while keeping
-- scan time bounded (cost scales linearly with window size).
--
-- Existing rows pick up the new default automatically. New datasets added
-- later can override per-row if needed.

ALTER TABLE datasets ADD COLUMN scan_window_hours REAL NOT NULL DEFAULT 6.0;
