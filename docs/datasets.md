# Datasets

[← Back to README](../README.md)

Eclipse catalogs are first-class entities in the database. The `datasets` table stores each catalog with a stable `slug`, human-readable `name`, `description`, and `source` URL. Every eclipse, run, result, and predicted reference row is keyed off `dataset_id` (replacing the older free-form `test_type` string). The admin UI exposes a **Datasets** list page and a per-dataset detail page that browses every eclipse in the catalog with its predicted geometry diagram and Saros context.

## NASA Five Millennium Canon of Eclipse Catalogs

The ground truth for eclipse occurrence comes from NASA's Goddard Space Flight Center eclipse catalogs compiled by Fred Espenak and Jean Meeus. These are the canonical reference catalogs used by the astronomy community.

**Solar eclipses (1901–2100):**
- [SE1901-2000.html](https://eclipse.gsfc.nasa.gov/SEcat5/SE1901-2000.html)
- [SE2001-2100.html](https://eclipse.gsfc.nasa.gov/SEcat5/SE2001-2100.html)

**Lunar eclipses (1901–2100):**
- [LE1901-2000.html](https://eclipse.gsfc.nasa.gov/LEcat5/LE1901-2000.html)
- [LE2001-2100.html](https://eclipse.gsfc.nasa.gov/LEcat5/LE2001-2100.html)

**Reference:** Espenak, F. and Meeus, J., [Five Millennium Canon of Solar Eclipses: -1999 to +3000](https://eclipse.gsfc.nasa.gov/SEpubs/5MCSE.html), NASA/TP-2006-214141

The script `scripts/parse_nasa_eclipses.py` fetches these HTML pages, extracts the fixed-width tabular data from `<pre>` blocks, parses each record's date/time, eclipse type, and magnitude, converts the timestamp to Julian Day (Terrestrial Time), and writes the result to `tests/data/solar_eclipses.json` and `tests/data/lunar_eclipses.json`.

Each record contains:
- `julian_day_tt` — Julian Day in Terrestrial Time (TT), the time scale used by the catalog
- `date` — ISO 8601 date/time string
- `type` — Normalized eclipse type (`total`, `annular`, `partial`, `hybrid`, `penumbral`)
- `magnitude` — Eclipse magnitude from the catalog
- `gamma` — Minimum distance of the shadow axis from Earth's center, in Earth radii (signed)
- `saros_num` — Saros series number, used for [series-level analysis](visualizations.md#saros-analysis)

## JPL DE440s Planetary Ephemeris

For each catalog eclipse, we compute the Sun and Moon positions as predicted by the standard heliocentric model using JPL's DE440 ephemeris via Skyfield. This provides an independent "where should the Sun and Moon actually be?" reference.

- **File:** `de440s.bsp` (compact version, auto-downloaded by Skyfield on first use)
- **Coverage:** 1849–2150 CE
- **Accuracy:** Sub-arcsecond for inner solar system bodies
- **Reference:** Park, R.S., et al., [The JPL Planetary and Lunar Ephemerides DE440 and DE441](https://doi.org/10.3847/1538-3881/abd414), The Astronomical Journal, 2021

The JPL data is precomputed at seed time (`server/seed.py`) and stored in the `jpl_reference` table, including Sun RA/Dec, Moon RA/Dec, Moon RA/Dec velocity, and angular separation — all computed at each catalog eclipse's Julian Day using Skyfield's `earth.at(t).observe()` method in the ICRF/J2000 frame.
