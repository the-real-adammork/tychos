# Parameter Sets

[← Back to README](../README.md)

On-disk store for Tychos orbital parameter sets. Each parameter set is a directory; each version inside it is a numbered JSON file. The seed script (`server/seed.py`) reads everything in this directory at first boot and writes it into the `param_sets` and `param_versions` tables.

## Layout

```
params/
└── <name>/
    ├── meta.json       # Set-level metadata
    ├── v1.json         # First version
    ├── v2.json         # Second version (parent: v1)
    └── v3.json         # ...
```

## `meta.json`

```json
{
  "name": "v1-original",
  "description": null,
  "forked_from": null
}
```

| Field | Type | Notes |
|---|---|---|
| `name` | string | Display name; matches the directory name |
| `description` | string \| null | Optional human description |
| `forked_from` | string \| null | Name of the parent param set, if this set was forked |

## `v<N>.json`

```json
{
  "version_number": 1,
  "parent": null,
  "notes": null,
  "params": {
    "earth":      { "orbit_radius": 37.8453, "orbit_center_a": 0, ... },
    "moon_def_a": { ... },
    "moon_def_b": { ... },
    "moon":       { ... },
    "sun_def":    { ... },
    "sun":        { ... },
    "mercury_def_a": { ... },
    ...
  }
}
```

| Field | Type | Notes |
|---|---|---|
| `version_number` | int | Sequential, starting at 1 |
| `parent` | int \| null | The previous version number, or null for v1 |
| `notes` | string \| null | Free-text description of what changed in this version |
| `params` | object | One key per celestial body, each containing the eight orbital parameters below |

### Per-body parameters

Every body in `params` is a flat object with these eight numeric fields:

| Field | Meaning |
|---|---|
| `orbit_radius` | Distance from the body's orbit center, in centi-AU (so 100 = one AU) |
| `orbit_center_a`, `orbit_center_b`, `orbit_center_c` | XYZ offset of the orbit center |
| `orbit_tilt_a`, `orbit_tilt_b` | Two tilt angles in degrees |
| `start_pos` | Starting angular position in degrees |
| `speed` | Angular speed in radians per year |

The body names match the hierarchy in `tychos_skyfield/baselib.py` — `earth`, `polar_axis`, `sun_def`, `sun`, `moon_def_a`, `moon_def_b`, `moon`, then deferents and bodies for each planet (Mercury through Neptune), Halley's comet, and Eros.

## How they get into the database

`server/seed.py::_seed_param_sets_from_disk` reads every directory in `params/`, loads `meta.json` and every `v<N>.json` it finds, and inserts them into:

- `param_sets` (one row per directory)
- `param_versions` (one row per `v<N>.json`)

It also auto-queues runs for the latest version against every dataset on first creation. Subsequent boots only insert new versions that aren't already in the database — existing rows aren't modified.

## Editing

The admin UI at `/parameters` is the supported way to edit parameter sets. The disk store is the seed source for new deployments and a snapshot of what shipped, but it doesn't sync back from the database — once seeded, the database is the source of truth.
