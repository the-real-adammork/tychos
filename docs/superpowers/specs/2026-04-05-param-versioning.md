# Parameter Versioning

## Data Model

```
ParamSet (named container)
  ├── id, name, description, owner_id, created_at
  │
  └── ParamVersion (each edit = new version)
       ├── id, param_set_id, version_number, params_md5, params_json, created_at
       │
       └── Run (linked to specific version)
            ├── id, param_version_id, test_type, status, ...
            └── EclipseResult (unchanged)
```

- ParamSet no longer stores params_json or params_md5
- ParamVersion stores the actual parameter values
- Run links to ParamVersion instead of ParamSet
- Creating a ParamVersion auto-queues solar + lunar runs

## Schema Changes

Drop `params_json`, `params_md5` from `param_sets`.
Add `param_versions` table.
Change `runs.param_set_id` → `runs.param_version_id`.

## API Changes

- POST /api/params — creates ParamSet + first ParamVersion + auto-queues 2 runs
- PUT /api/params/:id — creates new ParamVersion (if values changed) + auto-queues 2 runs
- GET /api/params/:id — returns ParamSet with latest version stats + version history
- POST /api/params/:id/fork — forks latest version into a new ParamSet
- POST /api/runs — kept for "force run" only
- GET /api/params/:id/versions — list all versions
- GET /api/params/:id/versions/:versionId — version detail with runs

## UI Changes

### Parameters list page
- Remove actions column
- Row click → param detail page
- Show name, owner, latest solar/lunar detection rates

### Param detail page (/parameters/:id)
- Stats cards at top: solar detection %, lunar detection %
- Run table: latest version's runs (solar + lunar rows)
- Version history table below
- Edit button → opens editor, saves creates new version + auto-runs
- Version row click → version detail page

### Version detail page (/parameters/:id/versions/:versionId)
- Same layout as param detail but for a specific version
- Stats at top, run rows below
- No version history (only relevant on parent)
- No edit button
