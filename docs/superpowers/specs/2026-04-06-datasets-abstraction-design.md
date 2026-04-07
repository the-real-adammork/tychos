# Datasets Abstraction

Replace the hardcoded `test_type` string pattern with a first-class `datasets` table that serves as the registry for all celestial event types. This makes the system extensible to new event types beyond solar/lunar eclipses.

## Schema Changes

### New table: `datasets`

```sql
CREATE TABLE datasets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL UNIQUE,          -- e.g. 'solar_eclipse', 'lunar_eclipse'
    name TEXT NOT NULL,                 -- display name, e.g. 'NASA Solar Eclipses'
    event_type TEXT NOT NULL,           -- e.g. 'solar_eclipse', 'lunar_eclipse'
    source_url TEXT,                    -- optional, e.g. NASA catalog URL
    description TEXT,                   -- optional
    record_count INTEGER DEFAULT 0,    -- denormalized, updated by seed
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

Seeded with two rows:

| slug | name | event_type | source_url |
|------|------|------------|------------|
| `solar_eclipse` | NASA Solar Eclipses | `solar_eclipse` | `https://eclipse.gsfc.nasa.gov/SEcat5/` |
| `lunar_eclipse` | NASA Lunar Eclipses | `lunar_eclipse` | `https://eclipse.gsfc.nasa.gov/LEcat5/` |

### Modified table: `runs`

- **Drop** `test_type TEXT NOT NULL`
- **Add** `dataset_id INTEGER NOT NULL REFERENCES datasets(id)`

### Modified table: `eclipse_catalog`

- **Drop** `test_type TEXT NOT NULL`
- **Add** `dataset_id INTEGER NOT NULL REFERENCES datasets(id)`
- Update unique index: `(dataset_id, julian_day_tt)` replaces `(test_type, julian_day_tt)`
- Update type index: `(dataset_id, type)` replaces `(test_type, type)`

### Modified table: `jpl_reference`

- **Drop** `test_type TEXT NOT NULL`
- **Add** `dataset_id INTEGER NOT NULL REFERENCES datasets(id)`
- Update unique constraint to `(dataset_id, julian_day_tt)` — currently `julian_day_tt` is UNIQUE but that breaks when two datasets share a JD. Needs to become a composite unique.

## Migration Strategy

Single migration `007_datasets.sql`:

1. Create `datasets` table and insert the two seed rows.
2. For each of `runs`, `eclipse_catalog`, `jpl_reference`:
   - Add `dataset_id` column (nullable initially).
   - Backfill from the old `test_type` column using the `datasets` slug mapping: `'solar'` → solar_eclipse dataset id, `'lunar'` → lunar_eclipse dataset id.
   - SQLite doesn't support `DROP COLUMN` cleanly, so we recreate the tables without `test_type`: create new table, copy data, drop old, rename.

The `test_type` → `dataset.slug` mapping is: `'solar'` → `'solar_eclipse'`, `'lunar'` → `'lunar_eclipse'`.

## Server Changes

### `server/seed.py`

- New `_seed_datasets()` — runs before `_seed_eclipse_catalog` and `_seed_param_sets`. Inserts the two dataset rows (idempotent via `INSERT OR IGNORE` on slug). Updates `record_count` after catalog seed.
- `_seed_eclipse_catalog()` — uses `dataset_id` instead of `test_type` string. Looks up dataset by slug.
- `_seed_param_sets_from_disk()` and `_seed_missing_versions()` — queue runs with `dataset_id` instead of `test_type`. Loops over datasets from DB.
- `_seed_jpl_reference()` — iterates datasets from DB, queries `eclipse_catalog` by `dataset_id`.

### `server/services/scanner.py`

- `load_eclipse_catalog(dataset_id: int)` — takes dataset_id instead of test_type string.

### `server/worker.py`

- Joins `runs` → `datasets` to get `dataset.slug` (needed to know solar vs lunar scan logic).
- Passes `dataset_id` to `load_eclipse_catalog`.
- Uses `dataset_id` when querying `jpl_reference`.

### `server/api/runs_routes.py`

- `CreateRunBody` takes `dataset_id` instead of `test_type`.
- List/get queries join `datasets` to return `dataset_id`, `dataset_name`, `dataset_slug`.
- `VALID_TEST_TYPES` check replaced with dataset existence check.

### `server/api/eclipse_routes.py`

Rename to `server/api/dataset_routes.py`. Prefix becomes `/api/datasets`.

- `GET /api/datasets` — list all datasets with their metadata and record counts.
- `GET /api/datasets/summary` — same as current eclipse summary but keyed by dataset slug.
- `GET /api/datasets/{slug}` — paginated catalog data for a dataset, looked up by slug.

### `server/api/dashboard_routes.py`

- Best solar/lunar queries join `datasets` instead of filtering on `test_type` string.
- Recent runs include `dataset_name` and `dataset_slug`.

### `server/api/results_routes.py`

- Join `datasets` to get slug (needed for JPL reference lookup and response data).

### `server/api/compare_routes.py`

- `_get_latest_done_run` takes `dataset_id` instead of `test_type`.
- Compare endpoint receives dataset slugs.

### `server/api/params_routes.py`

- All places that loop `for test_type in ("solar", "lunar")` instead query datasets from DB and loop over them.
- Queued run creation uses `dataset_id`.
- Stats queries (solar_stats, lunar_stats) become keyed by dataset slug dynamically.

### `server/app.py`

- Replace `eclipse_router` import with `dataset_router`.

## Frontend Changes

### Sidebar (`sidebar.tsx`)

- Change "Eclipses" nav item to "Datasets" with `Database` icon, linking to `/datasets`.

### New page: `/datasets` (`DatasetsPage.tsx`)

Lists all datasets as cards. Each card shows: name, event_type, record_count, source_url link, description. Clicking navigates to `/datasets/:slug`.

### Renamed page: `/datasets/:slug` (`DatasetDetailPage.tsx`)

The current `EclipsesPage.tsx` renamed and updated:
- Fetches dataset metadata + paginated catalog data by slug.
- Solar/lunar tabs replaced by the slug route (each dataset is its own page).
- Table columns are driven by the dataset's event_type (solar columns vs lunar columns).

### Dashboard (`DashboardPage.tsx`, `eclipse-datasets.tsx`)

- Rename `EclipseDatasets` → `DatasetSummary`.
- Fetch from `/api/datasets/summary`, render one card per dataset.

### Run table (`run-table.tsx`)

- API now returns `dataset_name` and `dataset_slug` per run.
- "Dataset" column shows `dataset_name` (e.g. "NASA Solar Eclipses") and links to `/datasets/:slug`.

### All other pages referencing `testType` / `test_type`

- `ResultsPage`, `ResultDetailPage`, `ParamDetailPage`, `ParamVersionDetailPage`, `param-list`, `recent-runs`, `compare-view` — replace `test_type` / `testType` with `dataset_slug` / `datasetName` from the API response.

### Router (`App.tsx`)

- Remove `/eclipses/:type` route.
- Add `/datasets` and `/datasets/:slug` routes.

## Seed Data

The two initial datasets:

```json
[
  {
    "slug": "solar_eclipse",
    "name": "NASA Solar Eclipses",
    "event_type": "solar_eclipse",
    "source_url": "https://eclipse.gsfc.nasa.gov/SEcat5/",
    "description": "Five Millennium Canon of Solar Eclipses (1901-2100)"
  },
  {
    "slug": "lunar_eclipse",
    "name": "NASA Lunar Eclipses",
    "event_type": "lunar_eclipse",
    "source_url": "https://eclipse.gsfc.nasa.gov/LEcat5/",
    "description": "Five Millennium Canon of Lunar Eclipses (1901-2100)"
  }
]
```

## What Stays the Same

- `eclipse_catalog` table name — it still holds eclipse data, the name is fine.
- `parse_nasa_eclipses.py` script — still writes JSON files; the seed loads them into DB.
- The scanner logic (solar vs lunar scan functions) — keyed off `dataset.slug` internally.
- `jpl_reference` seeding logic — just uses `dataset_id` instead of `test_type` string.
