# Task 03: Parse NASA Eclipse Catalogs

**Plan:** test-plan.md
**Prerequisites:** task-01

## Objective

Create a script that downloads and parses the NASA Five Millennium Canon eclipse catalog files into JSON for use by the test suite.

## Steps

### 1. Examine the NASA catalog format

Fetch the catalog pages and determine the exact fixed-width format. The solar and lunar catalogs have different column layouts. Key fields to extract:
- Date and time of greatest eclipse (this is in TD/TT)
- Eclipse type (total, annular, partial, penumbral, etc.)
- Magnitude
- Julian day (may need to be computed from the date)

### 2. Create scripts/parse_nasa_eclipses.py

The script should:
- Download (or read from a local cache) the NASA catalog text files
- Parse the fixed-width columns
- Compute Julian day TT for each eclipse from the date/time fields
- Output JSON arrays to `tests/data/solar_eclipses.json` and `tests/data/lunar_eclipses.json`

Output schema per entry:
```json
{
  "julian_day_tt": 2451545.0,
  "date": "2000-01-01T12:00:00",
  "type": "total",
  "magnitude": 1.024
}
```

### 3. Run the parser and commit the JSON data files

The JSON files are committed to the repo so tests don't need network access at runtime.

## Verification

- [ ] `scripts/parse_nasa_eclipses.py` runs without errors
- [ ] `tests/data/solar_eclipses.json` exists and contains entries
- [ ] `tests/data/lunar_eclipses.json` exists and contains entries
- [ ] Spot-check a few entries against the NASA catalog by hand
- [ ] Each entry has `julian_day_tt`, `date`, `type`, and `magnitude` fields
