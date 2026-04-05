# Results Database & Parameter Versioning Plan

## Goal

Store multiple versions of Tychos orbital parameters as JSON in the repo, run eclipse tests against each version, and record all results in a SQLite database that ships as a GitHub Release artifact.

## Parameter Versioning

### Storage

```
params/
  v1-original.json          # current TSN parameters (baseline)
  v2-moon-adjustment.json   # example: tweaked moon orbit
  v3-mars-fix.json          # example: adjusted mars deferent
```

Each file is a complete parameter set in the same format as `tychos_skyfield/orbital_params.json`. There can be any number of versions — the test runner discovers all JSON files in `params/` and runs against each one, making it easy to compare competing sets of values side by side.

A new version can be created by copying an existing one and modifying values, or by running the sync script against a different TSN commit.

### Naming Convention

`v{N}-{short-description}.json` — sequential version number plus a human-readable tag. The version number is just for ordering; the filename is the unique identifier.

### Generating the Baseline

```bash
# Copy the current TSN-derived params as v1
cp tychos_skyfield/tychos_skyfield/orbital_params.json params/v1-original.json
```

New versions are created manually or by script — the repo tracks them as plain JSON, fully diffable in git.

## Results Database

### Schema

Three tables:

**param_sets** — stores the full parameter JSON so the db is self-contained
```sql
CREATE TABLE param_sets (
    param_set_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL UNIQUE,   -- e.g. "v1-original"
    params_md5    TEXT NOT NULL,          -- md5 of canonical JSON
    params_json   TEXT NOT NULL,          -- full JSON blob
    created_date  TEXT NOT NULL           -- ISO 8601 timestamp
);
```

**runs** — one row per test execution
```sql
CREATE TABLE runs (
    run_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    param_set_id   INTEGER NOT NULL REFERENCES param_sets(param_set_id),
    params_name    TEXT NOT NULL,         -- denormalized for query convenience
    test_type      TEXT NOT NULL,         -- "solar" or "lunar"
    code_version   TEXT NOT NULL,         -- manually bumped when algorithm changes
    run_date       TEXT NOT NULL,         -- ISO 8601 timestamp
    tsn_commit     TEXT,                  -- git rev-parse HEAD of TSN submodule
    tychos_skyfield_commit TEXT,          -- git rev-parse HEAD of tychos_skyfield
    total_eclipses INTEGER NOT NULL,
    detected       INTEGER NOT NULL
);
```

**eclipse_results** — one row per eclipse per run
```sql
CREATE TABLE eclipse_results (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id                INTEGER NOT NULL REFERENCES runs(run_id),
    julian_day_tt         REAL NOT NULL,          -- catalog eclipse time
    date                  TEXT NOT NULL,
    catalog_type          TEXT NOT NULL,
    magnitude             REAL NOT NULL,
    detected              INTEGER NOT NULL,       -- 1 or 0
    threshold_arcmin      REAL NOT NULL,           -- threshold used for detection
    min_separation_arcmin REAL,                     -- NULL if scan failed
    timing_offset_min     REAL,                     -- NULL if scan failed
    best_jd               REAL,                     -- JD at predicted minimum separation
    sun_ra_rad            REAL,                     -- Sun RA at predicted minimum (radians)
    sun_dec_rad           REAL,                     -- Sun Dec at predicted minimum (radians)
    moon_ra_rad           REAL,                     -- Moon RA at predicted minimum (radians)
    moon_dec_rad          REAL                      -- Moon Dec at predicted minimum (radians)
);
```

Storing the raw RA/Dec at the predicted minimum enables analysis of:
- **Error direction**: whether the Moon is consistently offset in RA vs Dec
- **Systematic biases** across eclipses and parameter versions
- **Position delta between versions**: how a parameter change shifts predictions

### MD5 Canonicalization

To avoid false mismatches from JSON formatting differences (trailing newlines, key ordering), the MD5 is always computed on the canonical form:

```python
hashlib.md5(json.dumps(json.load(f), sort_keys=True).encode()).hexdigest()
```

### Matching Logic

Parameter sets are matched by `params_md5` (content identity). If a JSON file is renamed but content is unchanged, it updates the existing `param_sets` row's name rather than creating a duplicate. If content changes but the name is reused, a new row is created (the UNIQUE constraint is on `name`, so the old row is updated with new content/md5).

### Initialization

On first run, if the db file doesn't exist:
1. Create the database and tables
2. Load all JSON files from `params/` into the `param_sets` table
3. Proceed with test runs

On subsequent runs, any new or modified JSON files in `params/` are synced into `param_sets` before testing.

### Transaction Safety

Each run (the `runs` row + all its `eclipse_results` rows) is inserted in a single transaction. If the runner crashes mid-eclipse, no partial data is committed.

### Location

The database file lives at `results/tychos_results.db`. It is gitignored — not tracked in the repo. It's either built locally by running tests, or downloaded from GitHub Releases.

### Artifact Publishing

```bash
# After running tests, publish the db
md5sum results/tychos_results.db > results/tychos_results.db.md5
gh release create v0.1 results/tychos_results.db results/tychos_results.db.md5 \
  --notes "Results for params v1-original through v3-mars-fix"

# Download on a fresh clone
gh release download --pattern "tychos_results.*" --dir results/
```

The md5 file is also uploaded as an artifact so anyone can verify the download.

## Test Runner

`run_eclipses.py` replaces the standalone `test_solar_eclipses.py` and `test_lunar_eclipses.py` scripts. The scan logic and threshold functions from those files move into `helpers.py`.

The scan functions return the predicted minimum separation, the Julian day it occurred at, and the Sun/Moon RA/Dec at that moment — all of which get stored in the database.

### CLI Usage

```bash
# Run all param versions, write to SQLite
python tests/run_eclipses.py

# Run a specific param version
python tests/run_eclipses.py params/v1-original.json

# Force re-run even if results exist
python tests/run_eclipses.py --force

# Run all and publish artifact
python tests/run_eclipses.py && ./scripts/publish_results.sh
```

### Behavior

1. Initialize/open the database, sync `params/` into `param_sets`
2. Discover all `params/*.json` files (or use the one specified)
3. For each params file and test type (solar, lunar):
   - Check if a run with this `params_md5 + test_type + code_version` already exists
   - If already run, skip (unless `--force`)
   - Load params as dict, pass to `TychosSystem(params=json.load(f))`
   - Run eclipse scan, insert all results in one transaction
   - Print summary
4. Print overall comparison across all param versions

### Commit Hashes

`tsn_commit` and `tychos_skyfield_commit` are populated by running `git -C <submodule> rev-parse HEAD` at runtime.

## Querying Results

Anyone with the database can query it directly:

```bash
# Compare detection rates across param versions
sqlite3 results/tychos_results.db "
  SELECT params_name, test_type, total_eclipses, detected,
         ROUND(100.0 * detected / total_eclipses, 1) AS pct
  FROM runs
  ORDER BY params_name, test_type;
"

# Find eclipses that v2 detects but v1 misses
sqlite3 results/tychos_results.db "
  SELECT a.date, a.catalog_type, a.min_separation_arcmin AS v1_sep,
         b.min_separation_arcmin AS v2_sep
  FROM eclipse_results a
  JOIN eclipse_results b ON a.julian_day_tt = b.julian_day_tt
  JOIN runs ra ON a.run_id = ra.run_id
  JOIN runs rb ON b.run_id = rb.run_id
  WHERE ra.params_name = 'v1-original'
    AND rb.params_name = 'v2-moon-adjustment'
    AND ra.test_type = rb.test_type
    AND a.detected = 0 AND b.detected = 1;
"
```

## Two Ways to Get Results

1. **Download the artifact** — `gh release download`, verify md5, query the db
2. **Run it yourself** — clone repo, `pip install -r requirements.txt`, `python tests/run_eclipses.py`, get the same db locally

Both paths produce the same data. The artifact is a convenience for people who don't want to wait for the test run.

## File Layout

```
tychos/
  params/
    v1-original.json
  results/
    tychos_results.db           # gitignored, built locally or downloaded
    tychos_results.db.md5       # gitignored, published with release
  scripts/
    parse_nasa_eclipses.py
    publish_results.sh
  tests/
    data/
      solar_eclipses.json
      lunar_eclipses.json
    conftest.py
    db.py                       # DB init, schema, insert helpers
    helpers.py                  # scan logic, angular separation, thresholds
    run_eclipses.py             # main test runner with SQLite output
    test_smoke.py
  .gitignore                    # includes results/*.db, results/*.md5
```
