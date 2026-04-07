# Datasets Abstraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace hardcoded `test_type` strings with a first-class `datasets` table, making the system extensible to new celestial event types.

**Architecture:** New `datasets` table becomes the central registry. All tables that previously used `test_type TEXT` (`runs`, `eclipse_catalog`, `jpl_reference`) get a `dataset_id INTEGER` FK instead. The migration recreates affected tables (SQLite has no DROP COLUMN). API and frontend are updated to use dataset slugs/names.

**Tech Stack:** SQLite migrations, Python/FastAPI, React/TypeScript (Vite SPA)

**Spec:** `docs/superpowers/specs/2026-04-06-datasets-abstraction-design.md`

---

### Task 1: Migration — Create `datasets` table and refactor FKs

**Files:**
- Create: `server/migrations/007_datasets.sql`

This is the most critical task. The migration must:
1. Create the `datasets` table with seed data
2. Recreate `runs`, `eclipse_catalog`, and `jpl_reference` without `test_type`, adding `dataset_id` FK
3. Backfill `dataset_id` from the old `test_type` values

- [ ] **Step 1: Write the migration SQL**

```sql
-- server/migrations/007_datasets.sql

-- 1. Create datasets table
CREATE TABLE datasets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    event_type TEXT NOT NULL,
    source_url TEXT,
    description TEXT,
    record_count INTEGER NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Seed the two initial datasets
INSERT INTO datasets (slug, name, event_type, source_url, description) VALUES
    ('solar_eclipse', 'NASA Solar Eclipses', 'solar_eclipse',
     'https://eclipse.gsfc.nasa.gov/SEcat5/',
     'Five Millennium Canon of Solar Eclipses (1901-2100)'),
    ('lunar_eclipse', 'NASA Lunar Eclipses', 'lunar_eclipse',
     'https://eclipse.gsfc.nasa.gov/LEcat5/',
     'Five Millennium Canon of Lunar Eclipses (1901-2100)');

-- 2. Recreate runs without test_type, with dataset_id FK
CREATE TABLE runs_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    param_version_id INTEGER NOT NULL REFERENCES param_versions(id) ON DELETE CASCADE,
    dataset_id INTEGER NOT NULL REFERENCES datasets(id),
    status TEXT NOT NULL DEFAULT 'queued',
    code_version TEXT NOT NULL DEFAULT '1.0',
    tsn_commit TEXT,
    skyfield_commit TEXT,
    total_eclipses INTEGER,
    detected INTEGER,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at DATETIME,
    completed_at DATETIME,
    error TEXT
);

INSERT INTO runs_new (id, param_version_id, dataset_id, status, code_version,
    tsn_commit, skyfield_commit, total_eclipses, detected,
    created_at, started_at, completed_at, error)
SELECT r.id, r.param_version_id,
    CASE r.test_type WHEN 'solar' THEN d_solar.id WHEN 'lunar' THEN d_lunar.id END,
    r.status, r.code_version, r.tsn_commit, r.skyfield_commit,
    r.total_eclipses, r.detected, r.created_at, r.started_at, r.completed_at, r.error
FROM runs r,
    (SELECT id FROM datasets WHERE slug = 'solar_eclipse') d_solar,
    (SELECT id FROM datasets WHERE slug = 'lunar_eclipse') d_lunar;

DROP TABLE runs;
ALTER TABLE runs_new RENAME TO runs;

-- 3. Recreate eclipse_catalog without test_type, with dataset_id FK
CREATE TABLE eclipse_catalog_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_id INTEGER NOT NULL REFERENCES datasets(id),
    catalog_number TEXT NOT NULL,
    julian_day_tt REAL NOT NULL,
    date TEXT NOT NULL,
    delta_t_s INTEGER,
    luna_num INTEGER,
    saros_num INTEGER,
    type_raw TEXT NOT NULL,
    type TEXT NOT NULL,
    gamma REAL,
    magnitude REAL NOT NULL,
    qle TEXT,
    lat INTEGER,
    lon INTEGER,
    sun_alt_deg INTEGER,
    path_width_km INTEGER,
    duration_s INTEGER,
    qse TEXT,
    pen_mag REAL,
    um_mag REAL,
    pen_duration_min REAL,
    par_duration_min REAL,
    total_duration_min REAL,
    zenith_lat INTEGER,
    zenith_lon INTEGER
);

INSERT INTO eclipse_catalog_new (id, dataset_id, catalog_number, julian_day_tt, date,
    delta_t_s, luna_num, saros_num, type_raw, type, gamma, magnitude,
    qle, lat, lon, sun_alt_deg, path_width_km, duration_s,
    qse, pen_mag, um_mag, pen_duration_min, par_duration_min,
    total_duration_min, zenith_lat, zenith_lon)
SELECT ec.id,
    CASE ec.test_type WHEN 'solar' THEN d_solar.id WHEN 'lunar' THEN d_lunar.id END,
    ec.catalog_number, ec.julian_day_tt, ec.date,
    ec.delta_t_s, ec.luna_num, ec.saros_num, ec.type_raw, ec.type,
    ec.gamma, ec.magnitude, ec.qle, ec.lat, ec.lon, ec.sun_alt_deg,
    ec.path_width_km, ec.duration_s, ec.qse, ec.pen_mag, ec.um_mag,
    ec.pen_duration_min, ec.par_duration_min, ec.total_duration_min,
    ec.zenith_lat, ec.zenith_lon
FROM eclipse_catalog ec,
    (SELECT id FROM datasets WHERE slug = 'solar_eclipse') d_solar,
    (SELECT id FROM datasets WHERE slug = 'lunar_eclipse') d_lunar;

DROP TABLE eclipse_catalog;
ALTER TABLE eclipse_catalog_new RENAME TO eclipse_catalog;

CREATE UNIQUE INDEX idx_eclipse_catalog_dataset_jd ON eclipse_catalog(dataset_id, julian_day_tt);
CREATE INDEX idx_eclipse_catalog_dataset_type ON eclipse_catalog(dataset_id, type);

-- 4. Recreate jpl_reference without test_type, with dataset_id FK
--    Also change unique constraint from julian_day_tt alone to (dataset_id, julian_day_tt)
CREATE TABLE jpl_reference_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_id INTEGER NOT NULL REFERENCES datasets(id),
    julian_day_tt REAL NOT NULL,
    sun_ra_rad REAL NOT NULL,
    sun_dec_rad REAL NOT NULL,
    moon_ra_rad REAL NOT NULL,
    moon_dec_rad REAL NOT NULL,
    separation_arcmin REAL NOT NULL,
    moon_ra_vel REAL,
    moon_dec_vel REAL
);

INSERT INTO jpl_reference_new (id, dataset_id, julian_day_tt,
    sun_ra_rad, sun_dec_rad, moon_ra_rad, moon_dec_rad,
    separation_arcmin, moon_ra_vel, moon_dec_vel)
SELECT j.id,
    CASE j.test_type WHEN 'solar' THEN d_solar.id WHEN 'lunar' THEN d_lunar.id END,
    j.julian_day_tt, j.sun_ra_rad, j.sun_dec_rad, j.moon_ra_rad, j.moon_dec_rad,
    j.separation_arcmin, j.moon_ra_vel, j.moon_dec_vel
FROM jpl_reference j,
    (SELECT id FROM datasets WHERE slug = 'solar_eclipse') d_solar,
    (SELECT id FROM datasets WHERE slug = 'lunar_eclipse') d_lunar;

DROP TABLE jpl_reference;
ALTER TABLE jpl_reference_new RENAME TO jpl_reference;

CREATE UNIQUE INDEX idx_jpl_reference_dataset_jd ON jpl_reference(dataset_id, julian_day_tt);

-- 5. Update record_count on datasets
UPDATE datasets SET record_count = (
    SELECT COUNT(*) FROM eclipse_catalog WHERE dataset_id = datasets.id
);
```

- [ ] **Step 2: Test the migration**

Back up the database, then run `init_db()` to apply the migration:

```bash
cp results/tychos_results.db results/tychos_results.db.bak
source tychos_skyfield/.venv/bin/activate
PYTHONPATH=tychos_skyfield:tests:. python3 -c "
from server.db import init_db
init_db()
"
```

Then verify:

```bash
sqlite3 results/tychos_results.db "
SELECT * FROM datasets;
SELECT COUNT(*) FROM runs WHERE dataset_id IS NOT NULL;
SELECT COUNT(*) FROM eclipse_catalog WHERE dataset_id IS NOT NULL;
SELECT COUNT(*) FROM jpl_reference WHERE dataset_id IS NOT NULL;
.schema runs
.schema eclipse_catalog
.schema jpl_reference
"
```

Expected: 2 datasets, all rows have dataset_id, no test_type column in any table.

- [ ] **Step 3: Commit**

```bash
git add server/migrations/007_datasets.sql
git commit -m "feat: add datasets table and migrate test_type to dataset_id FK"
```

---

### Task 2: Update seed.py

**Files:**
- Modify: `server/seed.py`

The seed needs to: create datasets first, then use dataset_id everywhere instead of test_type strings.

- [ ] **Step 1: Rewrite seed.py**

Replace the full file content. Key changes:
- Add `_seed_datasets()` as first seed step
- `_seed_eclipse_catalog()` looks up dataset by slug, uses dataset_id
- `_seed_param_sets_from_disk()` and `_seed_missing_versions()` query all datasets, queue runs with dataset_id
- `_seed_jpl_reference()` queries datasets, uses dataset_id

```python
# server/seed.py
"""Seed the database with admin user, datasets, params, and JPL reference data.

Called automatically by init_db() after migrations. Idempotent.
"""
import hashlib
import json
import os
import sys
from pathlib import Path

import bcrypt
import numpy as np

from server.db import get_db
from server.params_store import load_all_param_sets

DATA_DIR = Path(__file__).parent.parent / "tests" / "data"

sys.path.insert(0, str(Path(__file__).parent.parent / "tychos_skyfield"))
sys.path.insert(0, str(Path(__file__).parent.parent / "tests"))


def seed():
    _seed_admin_user()
    _seed_datasets()
    _seed_param_sets_from_disk()
    _seed_eclipse_catalog()
    _seed_jpl_reference()


def _seed_admin_user():
    admin_email = os.environ.get("TYCHOS_ADMIN_USER", "admin@tychos.local")
    admin_password = os.environ.get("TYCHOS_ADMIN_PASSWORD", "admin")

    with get_db() as conn:
        existing = conn.execute("SELECT id FROM users WHERE email = ?", (admin_email,)).fetchone()
        if existing:
            return
        password_hash = bcrypt.hashpw(admin_password.encode(), bcrypt.gensalt()).decode()
        conn.execute(
            "INSERT INTO users (email, name, password_hash) VALUES (?, ?, ?)",
            (admin_email, "Admin", password_hash),
        )
        conn.commit()
        print(f"[seed] Created admin user ({admin_email})")


DATASET_SEEDS = [
    {
        "slug": "solar_eclipse",
        "name": "NASA Solar Eclipses",
        "event_type": "solar_eclipse",
        "source_url": "https://eclipse.gsfc.nasa.gov/SEcat5/",
        "description": "Five Millennium Canon of Solar Eclipses (1901-2100)",
        "catalog_file": "solar_eclipses.json",
    },
    {
        "slug": "lunar_eclipse",
        "name": "NASA Lunar Eclipses",
        "event_type": "lunar_eclipse",
        "source_url": "https://eclipse.gsfc.nasa.gov/LEcat5/",
        "description": "Five Millennium Canon of Lunar Eclipses (1901-2100)",
        "catalog_file": "lunar_eclipses.json",
    },
]


def _seed_datasets():
    """Ensure dataset rows exist. Idempotent via INSERT OR IGNORE on slug."""
    with get_db() as conn:
        for ds in DATASET_SEEDS:
            conn.execute(
                """INSERT OR IGNORE INTO datasets (slug, name, event_type, source_url, description)
                   VALUES (?, ?, ?, ?, ?)""",
                (ds["slug"], ds["name"], ds["event_type"], ds["source_url"], ds["description"]),
            )
        conn.commit()


def _get_all_datasets(conn) -> list[dict]:
    """Return all dataset rows as dicts."""
    rows = conn.execute("SELECT * FROM datasets ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def _seed_param_sets_from_disk():
    """Seed all param sets and versions from JSON files in params/ directory."""
    param_sets = load_all_param_sets()
    if not param_sets:
        return

    with get_db() as conn:
        admin_email = os.environ.get("TYCHOS_ADMIN_USER", "admin@tychos.local")
        user = conn.execute("SELECT id FROM users WHERE email = ?", (admin_email,)).fetchone()
        if not user:
            return

        datasets = _get_all_datasets(conn)
        name_to_id = {}

        for ps in param_sets:
            existing = conn.execute("SELECT id FROM param_sets WHERE name = ?", (ps["name"],)).fetchone()
            if existing:
                name_to_id[ps["name"]] = existing["id"]
                _seed_missing_versions(conn, existing["id"], ps["name"], ps["versions"], datasets)
                continue

            forked_from_id = name_to_id.get(ps.get("forked_from")) if ps.get("forked_from") else None

            cur = conn.execute(
                "INSERT INTO param_sets (name, description, owner_id, forked_from_id) VALUES (?, ?, ?, ?)",
                (ps["name"], ps.get("description"), user["id"], forked_from_id),
            )
            param_set_id = cur.lastrowid
            name_to_id[ps["name"]] = param_set_id

            prev_version_id = None
            for ver in ps["versions"]:
                params_json = json.dumps(ver["params"], sort_keys=True)
                params_md5 = hashlib.md5(params_json.encode()).hexdigest()

                cur = conn.execute(
                    "INSERT INTO param_versions (param_set_id, version_number, parent_version_id, params_md5, params_json, notes) VALUES (?, ?, ?, ?, ?, ?)",
                    (param_set_id, ver["version_number"], prev_version_id, params_md5, params_json, ver.get("notes")),
                )
                version_id = cur.lastrowid
                prev_version_id = version_id

                if ver == ps["versions"][-1]:
                    for ds in datasets:
                        conn.execute(
                            "INSERT INTO runs (param_version_id, dataset_id, status) VALUES (?, ?, 'queued')",
                            (version_id, ds["id"]),
                        )

            conn.commit()
            print(f"[seed] Created {ps['name']} with {len(ps['versions'])} version(s) and {len(datasets)} queued runs")


def _seed_missing_versions(conn, param_set_id: int, name: str, versions: list[dict], datasets: list[dict]):
    """Seed any versions from disk that don't yet exist in the DB."""
    existing_nums = {
        row[0]
        for row in conn.execute(
            "SELECT version_number FROM param_versions WHERE param_set_id = ?", (param_set_id,)
        ).fetchall()
    }

    prev_cursor = conn.execute(
        "SELECT id FROM param_versions WHERE param_set_id = ? ORDER BY version_number DESC LIMIT 1",
        (param_set_id,),
    )
    prev_row = prev_cursor.fetchone()
    prev_version_id = prev_row["id"] if prev_row else None

    added = 0
    for ver in versions:
        if ver["version_number"] in existing_nums:
            row = conn.execute(
                "SELECT id FROM param_versions WHERE param_set_id = ? AND version_number = ?",
                (param_set_id, ver["version_number"]),
            ).fetchone()
            if row:
                prev_version_id = row["id"]
            continue

        params_json = json.dumps(ver["params"], sort_keys=True)
        params_md5 = hashlib.md5(params_json.encode()).hexdigest()

        cur = conn.execute(
            "INSERT INTO param_versions (param_set_id, version_number, parent_version_id, params_md5, params_json, notes) VALUES (?, ?, ?, ?, ?, ?)",
            (param_set_id, ver["version_number"], prev_version_id, params_md5, params_json, ver.get("notes")),
        )
        prev_version_id = cur.lastrowid
        added += 1

        for ds in datasets:
            conn.execute(
                "INSERT INTO runs (param_version_id, dataset_id, status) VALUES (?, ?, 'queued')",
                (prev_version_id, ds["id"]),
            )

    if added:
        conn.commit()
        print(f"[seed] Added {added} new version(s) to {name}")


def _seed_eclipse_catalog():
    """Load NASA eclipse catalog JSON into the eclipse_catalog table.

    Idempotent via INSERT OR IGNORE on the unique (dataset_id, julian_day_tt) index.
    """
    with get_db() as conn:
        initial_count = conn.execute("SELECT COUNT(*) FROM eclipse_catalog").fetchone()[0]

    total_inserted = 0
    for ds_seed in DATASET_SEEDS:
        catalog_path = DATA_DIR / ds_seed["catalog_file"]
        if not catalog_path.exists():
            continue
        with open(catalog_path) as f:
            catalog = json.load(f)

        with get_db() as conn:
            ds_row = conn.execute("SELECT id FROM datasets WHERE slug = ?", (ds_seed["slug"],)).fetchone()
            if not ds_row:
                continue
            dataset_id = ds_row["id"]

            rows = []
            for ecl in catalog:
                rows.append((
                    dataset_id,
                    ecl.get("catalog_number"),
                    ecl["julian_day_tt"],
                    ecl["date"],
                    ecl.get("delta_t_s"),
                    ecl.get("luna_num"),
                    ecl.get("saros_num"),
                    ecl.get("type_raw", ""),
                    ecl.get("type", "unknown"),
                    ecl.get("gamma"),
                    ecl.get("magnitude"),
                    ecl.get("qle"),
                    ecl.get("lat"),
                    ecl.get("lon"),
                    ecl.get("sun_alt_deg"),
                    ecl.get("path_width_km"),
                    ecl.get("duration_s"),
                    ecl.get("qse"),
                    ecl.get("pen_mag"),
                    ecl.get("um_mag"),
                    ecl.get("pen_duration_min"),
                    ecl.get("par_duration_min"),
                    ecl.get("total_duration_min"),
                    ecl.get("zenith_lat"),
                    ecl.get("zenith_lon"),
                ))

            conn.executemany(
                """INSERT OR IGNORE INTO eclipse_catalog
                   (dataset_id, catalog_number, julian_day_tt, date, delta_t_s,
                    luna_num, saros_num, type_raw, type, gamma, magnitude,
                    qle, lat, lon, sun_alt_deg, path_width_km, duration_s,
                    qse, pen_mag, um_mag, pen_duration_min, par_duration_min,
                    total_duration_min, zenith_lat, zenith_lon)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                rows,
            )
            conn.commit()

            # Update record_count
            count = conn.execute("SELECT COUNT(*) FROM eclipse_catalog WHERE dataset_id = ?", (dataset_id,)).fetchone()[0]
            conn.execute("UPDATE datasets SET record_count = ? WHERE id = ?", (count, dataset_id))
            conn.commit()
            total_inserted += count

    if initial_count == 0 and total_inserted > 0:
        print(f"[seed] Loaded {total_inserted} eclipse catalog entries")


def _seed_jpl_reference():
    """Precompute JPL/Skyfield Sun+Moon positions for all catalog eclipses.

    Only runs once — skips if jpl_reference table already has data.
    """
    with get_db() as conn:
        count = conn.execute("SELECT COUNT(*) FROM jpl_reference").fetchone()[0]
        if count > 0:
            return

    print("[seed] Computing JPL reference positions (this takes a moment)...")

    from skyfield.api import load as skyfield_load
    from helpers import angular_separation

    eph = skyfield_load("de440s.bsp")
    ts = skyfield_load.timescale()
    earth = eph["earth"]

    rows = []
    with get_db() as conn:
        datasets = _get_all_datasets(conn)
        for ds in datasets:
            eclipses = conn.execute(
                "SELECT julian_day_tt FROM eclipse_catalog WHERE dataset_id = ? ORDER BY julian_day_tt",
                (ds["id"],),
            ).fetchall()

            for ecl in eclipses:
                jd = ecl["julian_day_tt"]
                t = ts.tt_jd(jd)
                t2 = ts.tt_jd(jd + 1.0 / 24.0)

                sun_ra, sun_dec, _ = earth.at(t).observe(eph["sun"]).radec()
                moon_ra, moon_dec, _ = earth.at(t).observe(eph["moon"]).radec()
                moon_ra2, moon_dec2, _ = earth.at(t2).observe(eph["moon"]).radec()

                s_ra, s_dec = sun_ra.radians, sun_dec.radians
                m_ra, m_dec = moon_ra.radians, moon_dec.radians
                m_ra_vel = float(moon_ra2.radians - m_ra)
                m_dec_vel = float(moon_dec2.radians - m_dec)
                sep = float(np.degrees(angular_separation(s_ra, s_dec, m_ra, m_dec)) * 60)

                rows.append((ds["id"], jd, float(s_ra), float(s_dec), float(m_ra), float(m_dec), round(sep, 2), m_ra_vel, m_dec_vel))

    with get_db() as conn:
        conn.executemany(
            """INSERT OR IGNORE INTO jpl_reference
               (dataset_id, julian_day_tt, sun_ra_rad, sun_dec_rad, moon_ra_rad, moon_dec_rad, separation_arcmin, moon_ra_vel, moon_dec_vel)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        conn.commit()

    print(f"[seed] Computed {len(rows)} JPL reference positions")
```

- [ ] **Step 2: Test the seed**

```bash
source tychos_skyfield/.venv/bin/activate
PYTHONPATH=tychos_skyfield:tests:. python3 -c "
from server.db import init_db
init_db()
import sqlite3
conn = sqlite3.connect('results/tychos_results.db')
print('datasets:', conn.execute('SELECT slug, record_count FROM datasets').fetchall())
print('runs:', conn.execute('SELECT COUNT(*) FROM runs').fetchone()[0])
print('catalog:', conn.execute('SELECT COUNT(*) FROM eclipse_catalog').fetchone()[0])
conn.close()
"
```

- [ ] **Step 3: Commit**

```bash
git add server/seed.py
git commit -m "feat: update seed to use datasets table with dataset_id FK"
```

---

### Task 3: Update scanner and worker

**Files:**
- Modify: `server/services/scanner.py`
- Modify: `server/worker.py`

- [ ] **Step 1: Update scanner.py**

Change `load_eclipse_catalog` to take `dataset_id`:

```python
# server/services/scanner.py
"""Eclipse scanning service — thin wrapper around tests/helpers.py logic."""
import numpy as np

from tychos_skyfield import baselib as T
from helpers import (
    scan_min_separation,
    scan_lunar_eclipse,
    lunar_threshold,
    SOLAR_DETECTION_THRESHOLD,
    MINUTE_IN_DAYS,
)

from server.db import get_db

HOUR_IN_DAYS = 1.0 / 24.0


def _tychos_moon_velocity(system, jd, m_ra, m_dec):
    """Compute Moon RA/Dec velocity (radians per hour) at the given JD."""
    system.move_system(jd + HOUR_IN_DAYS)
    m_ra2, m_dec2, _ = system['moon'].radec_direct(system['earth'], epoch='j2000', formatted=False)
    system.move_system(jd)
    return float(m_ra2 - m_ra), float(m_dec2 - m_dec)


def load_eclipse_catalog(dataset_id: int) -> list[dict]:
    """Load eclipse catalog entries for a dataset from the DB."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT julian_day_tt, date, type, magnitude FROM eclipse_catalog WHERE dataset_id = ? ORDER BY julian_day_tt",
            (dataset_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def scan_solar_eclipses(params: dict, eclipses: list[dict]) -> list[dict]:
    """Run solar eclipse scan for the given params and eclipse list."""
    system = T.TychosSystem(params=params)
    threshold_arcmin = np.degrees(SOLAR_DETECTION_THRESHOLD) * 60
    rows = []

    for ecl in eclipses:
        jd = ecl["julian_day_tt"]
        min_sep, best_jd, s_ra, s_dec, m_ra, m_dec = scan_min_separation(system, jd)
        det = min_sep < SOLAR_DETECTION_THRESHOLD
        m_ra_vel, m_dec_vel = _tychos_moon_velocity(system, best_jd, float(m_ra), float(m_dec))

        rows.append({
            "julian_day_tt": jd,
            "date": ecl["date"],
            "catalog_type": ecl["type"],
            "magnitude": ecl["magnitude"],
            "detected": 1 if det else 0,
            "threshold_arcmin": round(threshold_arcmin, 4),
            "min_separation_arcmin": round(np.degrees(min_sep) * 60, 2),
            "timing_offset_min": round((best_jd - jd) / MINUTE_IN_DAYS, 1),
            "best_jd": best_jd,
            "sun_ra_rad": float(s_ra),
            "sun_dec_rad": float(s_dec),
            "moon_ra_rad": float(m_ra),
            "moon_dec_rad": float(m_dec),
            "moon_ra_vel": m_ra_vel,
            "moon_dec_vel": m_dec_vel,
        })

    return rows


def scan_lunar_eclipses(params: dict, eclipses: list[dict]) -> list[dict]:
    """Run lunar eclipse scan for the given params and eclipse list."""
    system = T.TychosSystem(params=params)
    rows = []

    for ecl in eclipses:
        jd = ecl["julian_day_tt"]
        min_sep, best_jd, s_ra, s_dec, m_ra, m_dec = scan_lunar_eclipse(system, jd)
        threshold = lunar_threshold(ecl["type"])
        threshold_arcmin = np.degrees(threshold) * 60
        det = min_sep < threshold
        m_ra_vel, m_dec_vel = _tychos_moon_velocity(system, best_jd, float(m_ra), float(m_dec))

        rows.append({
            "julian_day_tt": jd,
            "date": ecl["date"],
            "catalog_type": ecl["type"],
            "magnitude": ecl["magnitude"],
            "detected": 1 if det else 0,
            "threshold_arcmin": round(threshold_arcmin, 4),
            "min_separation_arcmin": round(np.degrees(min_sep) * 60, 2),
            "timing_offset_min": round((best_jd - jd) / MINUTE_IN_DAYS, 1),
            "best_jd": best_jd,
            "sun_ra_rad": float(s_ra),
            "sun_dec_rad": float(s_dec),
            "moon_ra_rad": float(m_ra),
            "moon_dec_rad": float(m_dec),
            "moon_ra_vel": m_ra_vel,
            "moon_dec_vel": m_dec_vel,
        })

    return rows
```

- [ ] **Step 2: Update worker.py**

The worker must join `datasets` to get the slug (for choosing solar vs lunar scan), and use `dataset_id` for JPL lookup:

```python
# server/worker.py
"""Background worker thread that processes queued eclipse runs."""
import json
import math
import time
import threading
import traceback
from datetime import datetime, timezone

from server.db import get_db
from server.services.scanner import (
    load_eclipse_catalog,
    scan_solar_eclipses,
    scan_lunar_eclipses,
)

_POLL_INTERVAL = 5


def _angular_sep_arcmin(ra1, dec1, ra2, dec2):
    """Vincenty angular separation in arcminutes."""
    dra = ra2 - ra1
    num = math.sqrt(
        (math.cos(dec2) * math.sin(dra)) ** 2
        + (math.cos(dec1) * math.sin(dec2) - math.sin(dec1) * math.cos(dec2) * math.cos(dra)) ** 2
    )
    den = math.sin(dec1) * math.sin(dec2) + math.cos(dec1) * math.cos(dec2) * math.cos(dra)
    return math.degrees(math.atan2(num, den)) * 60


def start_worker() -> threading.Thread:
    """Start a daemon thread running the worker loop. Returns the thread."""
    t = threading.Thread(target=_worker_loop, daemon=True, name="eclipse-worker")
    t.start()
    return t


def _worker_loop() -> None:
    """Infinite loop: process one queued run, then sleep."""
    while True:
        try:
            _process_one()
        except Exception:
            print(f"[worker] Unexpected loop error:\n{traceback.format_exc()}")
        time.sleep(_POLL_INTERVAL)


def _process_one() -> None:
    """Pick up the oldest queued run, execute it, and write results."""
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT r.id, r.dataset_id, d.slug AS dataset_slug, pv.params_json
              FROM runs r
              JOIN param_versions pv ON r.param_version_id = pv.id
              JOIN datasets d ON r.dataset_id = d.id
             WHERE r.status = 'queued'
             ORDER BY r.created_at ASC
             LIMIT 1
            """
        ).fetchone()

        if row is None:
            return

        run_id = row["id"]
        dataset_id = row["dataset_id"]
        dataset_slug = row["dataset_slug"]
        params = json.loads(row["params_json"])

    with get_db() as conn:
        conn.execute(
            "UPDATE runs SET status = 'running', started_at = ? WHERE id = ?",
            (_now(), run_id),
        )
        conn.commit()

    try:
        eclipses = load_eclipse_catalog(dataset_id)

        if dataset_slug == "solar_eclipse":
            results = scan_solar_eclipses(params, eclipses)
        elif dataset_slug == "lunar_eclipse":
            results = scan_lunar_eclipses(params, eclipses)
        else:
            raise ValueError(f"Unknown dataset slug: {dataset_slug}")

        detected = sum(1 for r in results if r["detected"])

        with get_db() as conn:
            jpl_rows = conn.execute(
                "SELECT julian_day_tt, moon_ra_rad, moon_dec_rad FROM jpl_reference WHERE dataset_id = ?",
                (dataset_id,),
            ).fetchall()
        jpl_by_jd = {row["julian_day_tt"]: row for row in jpl_rows}

        for r in results:
            jpl = jpl_by_jd.get(r["julian_day_tt"])
            if jpl and r["moon_ra_rad"] is not None and r["moon_dec_rad"] is not None:
                r["moon_error_arcmin"] = round(_angular_sep_arcmin(
                    r["moon_ra_rad"], r["moon_dec_rad"],
                    jpl["moon_ra_rad"], jpl["moon_dec_rad"],
                ), 2)
            else:
                r["moon_error_arcmin"] = None

        CHUNK_SIZE = 50
        insert_sql = """
            INSERT INTO eclipse_results (
                run_id, julian_day_tt, date, catalog_type, magnitude,
                detected, threshold_arcmin, min_separation_arcmin,
                timing_offset_min, best_jd,
                sun_ra_rad, sun_dec_rad, moon_ra_rad, moon_dec_rad,
                moon_error_arcmin, moon_ra_vel, moon_dec_vel
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        rows = [
            (
                run_id,
                r["julian_day_tt"], r["date"], r["catalog_type"], r["magnitude"],
                r["detected"], r["threshold_arcmin"], r["min_separation_arcmin"],
                r["timing_offset_min"], r["best_jd"],
                r["sun_ra_rad"], r["sun_dec_rad"], r["moon_ra_rad"], r["moon_dec_rad"],
                r["moon_error_arcmin"], r.get("moon_ra_vel"), r.get("moon_dec_vel"),
            )
            for r in results
        ]
        for i in range(0, len(rows), CHUNK_SIZE):
            chunk = rows[i : i + CHUNK_SIZE]
            with get_db() as conn:
                conn.executemany(insert_sql, chunk)
                conn.commit()

        with get_db() as conn:
            conn.execute(
                """
                UPDATE runs
                   SET status = 'done',
                       completed_at = ?,
                       total_eclipses = ?,
                       detected = ?
                 WHERE id = ?
                """,
                (_now(), len(results), detected, run_id),
            )
            conn.commit()

        print(f"[worker] Run {run_id} complete: {detected}/{len(results)}")

    except Exception as exc:
        error_text = traceback.format_exc()[:2000]
        with get_db() as conn:
            conn.execute(
                """
                UPDATE runs
                   SET status = 'failed',
                       error = ?,
                       completed_at = ?
                 WHERE id = ?
                """,
                (error_text, _now(), run_id),
            )
            conn.commit()
        print(f"[worker] Run {run_id} failed: {exc}")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    from server.db import init_db
    init_db()
    print("[worker] Starting standalone worker process")
    _worker_loop()
```

- [ ] **Step 3: Commit**

```bash
git add server/services/scanner.py server/worker.py
git commit -m "feat: update scanner and worker to use dataset_id"
```

---

### Task 4: Update all server API routes

**Files:**
- Modify: `server/api/runs_routes.py`
- Modify: `server/api/results_routes.py`
- Modify: `server/api/dashboard_routes.py`
- Modify: `server/api/compare_routes.py`
- Modify: `server/api/params_routes.py`
- Rename: `server/api/eclipse_routes.py` → `server/api/dataset_routes.py`
- Modify: `server/app.py`

This is the largest task. Every API that referenced `test_type` must use `dataset_id` / `dataset_slug` instead. Each file is shown in full below.

- [ ] **Step 1: Create dataset_routes.py (replacing eclipse_routes.py)**

```python
# server/api/dataset_routes.py
"""Dataset routes: list datasets and browse catalog data."""
from fastapi import APIRouter, HTTPException, Query

from server.db import get_async_db

router = APIRouter(prefix="/api/datasets")


@router.get("")
async def list_datasets():
    """Return all datasets with metadata."""
    async with get_async_db() as conn:
        cursor = await conn.execute("SELECT * FROM datasets ORDER BY id")
        rows = await cursor.fetchall()
    return [dict(r) for r in rows]


@router.get("/summary")
async def dataset_summary():
    """Return summary stats for all datasets, keyed by slug."""
    async with get_async_db() as conn:
        ds_cursor = await conn.execute("SELECT id, slug FROM datasets ORDER BY id")
        datasets = await ds_cursor.fetchall()

        results = {}
        for ds in datasets:
            type_cursor = await conn.execute(
                """
                SELECT type AS catalog_type, COUNT(*) AS count
                FROM eclipse_catalog
                WHERE dataset_id = ?
                GROUP BY type
                ORDER BY count DESC
                """,
                (ds["id"],),
            )
            breakdown = [dict(r) for r in await type_cursor.fetchall()]

            count_cursor = await conn.execute(
                "SELECT COUNT(*) FROM eclipse_catalog WHERE dataset_id = ?",
                (ds["id"],),
            )
            total = (await count_cursor.fetchone())[0]

            results[ds["slug"]] = {"total": total, "breakdown": breakdown}

    return results


@router.get("/{slug}")
async def get_dataset_catalog(
    slug: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    catalog_type: str | None = Query(default=None),
):
    """Return paginated catalog data for a dataset by slug."""
    async with get_async_db() as conn:
        ds_cursor = await conn.execute(
            "SELECT id, slug, event_type FROM datasets WHERE slug = ?", (slug,)
        )
        ds = await ds_cursor.fetchone()
        if not ds:
            raise HTTPException(status_code=404, detail=f"Dataset '{slug}' not found")

        dataset_id = ds["id"]
        event_type = ds["event_type"]
        offset = (page - 1) * page_size

        conditions = ["dataset_id = ?"]
        values: list = [dataset_id]

        if catalog_type:
            conditions.append("type = ?")
            values.append(catalog_type)

        where = " AND ".join(conditions)

        count_cursor = await conn.execute(
            f"SELECT COUNT(*) FROM eclipse_catalog WHERE {where}", values
        )
        total = (await count_cursor.fetchone())[0]

        if event_type == "solar_eclipse":
            cols = """id, catalog_number, julian_day_tt, date, delta_t_s,
                      luna_num, saros_num, type_raw, type, qle, gamma,
                      magnitude, lat, lon, sun_alt_deg, path_width_km, duration_s"""
        else:
            cols = """id, catalog_number, julian_day_tt, date, delta_t_s,
                      luna_num, saros_num, type_raw, type, qse, gamma,
                      pen_mag, um_mag, magnitude,
                      pen_duration_min, par_duration_min, total_duration_min,
                      zenith_lat, zenith_lon"""

        cursor = await conn.execute(
            f"""
            SELECT {cols}
            FROM eclipse_catalog
            WHERE {where}
            ORDER BY julian_day_tt
            LIMIT ? OFFSET ?
            """,
            values + [page_size, offset],
        )
        rows = [dict(r) for r in await cursor.fetchall()]

    return {
        "eclipses": rows,
        "total": total,
        "page": page,
        "page_size": page_size,
        "event_type": event_type,
    }
```

- [ ] **Step 2: Delete old eclipse_routes.py**

```bash
rm server/api/eclipse_routes.py
```

- [ ] **Step 3: Update runs_routes.py**

Replace `test_type` with `dataset_id` in create, and join datasets in list/get:

```python
# server/api/runs_routes.py
"""Run routes: list, create, get."""
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from server.auth import require_user
from server.db import get_async_db

router = APIRouter(prefix="/api/runs")


def _row_to_dict(row) -> dict:
    return dict(row)


@router.get("")
async def list_runs(
    param_set_id: int | None = Query(default=None),
    status: str | None = Query(default=None),
):
    """List runs with param set and dataset info."""
    conditions = []
    values: list = []

    if param_set_id is not None:
        conditions.append("pv.param_set_id = ?")
        values.append(param_set_id)
    if status is not None:
        conditions.append("r.status = ?")
        values.append(status)

    where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    async with get_async_db() as conn:
        cursor = await conn.execute(
            f"""
            SELECT r.*, pv.version_number, ps.id AS param_set_id, ps.name AS param_set_name,
                   u.name AS owner_name, d.slug AS dataset_slug, d.name AS dataset_name
            FROM runs r
            JOIN param_versions pv ON r.param_version_id = pv.id
            JOIN param_sets ps ON pv.param_set_id = ps.id
            JOIN users u ON ps.owner_id = u.id
            JOIN datasets d ON r.dataset_id = d.id
            {where_clause}
            ORDER BY r.created_at DESC
            LIMIT 100
            """,
            values,
        )
        rows = await cursor.fetchall()

        result = []
        for row in rows:
            d = _row_to_dict(row)
            if d["status"] == "done":
                op_cursor = await conn.execute(
                    """
                    SELECT SUM(CASE WHEN detected = 1 OR (moon_error_arcmin IS NOT NULL AND moon_error_arcmin < 60) THEN 1 ELSE 0 END) AS overall_pass
                    FROM eclipse_results WHERE run_id = ?
                    """,
                    (d["id"],),
                )
                op_row = await op_cursor.fetchone()
                d["overall_pass"] = op_row["overall_pass"] or 0
            else:
                d["overall_pass"] = None
            result.append(d)

    return result


class CreateRunBody(BaseModel):
    param_set_id: int
    dataset_id: int


@router.post("", status_code=201)
async def create_run(body: CreateRunBody, request: Request):
    """Queue a new run for the latest version of a param set + dataset. Auth required."""
    user = await require_user(request)

    async with get_async_db() as conn:
        # Validate dataset exists
        ds_cursor = await conn.execute("SELECT id FROM datasets WHERE id = ?", (body.dataset_id,))
        if await ds_cursor.fetchone() is None:
            raise HTTPException(status_code=404, detail="Dataset not found")

        # Find latest version for this param set
        ver_cursor = await conn.execute(
            """
            SELECT id FROM param_versions
            WHERE param_set_id = ?
            ORDER BY version_number DESC
            LIMIT 1
            """,
            (body.param_set_id,),
        )
        latest_ver = await ver_cursor.fetchone()
        if latest_ver is None:
            raise HTTPException(status_code=404, detail="Param set not found or has no versions")

        param_version_id = latest_ver["id"]

        cursor = await conn.execute(
            """
            INSERT INTO runs (param_version_id, dataset_id, status)
            VALUES (?, ?, 'queued')
            """,
            (param_version_id, body.dataset_id),
        )
        await conn.commit()

        row_cursor = await conn.execute(
            """
            SELECT r.*, pv.version_number, ps.id AS param_set_id, ps.name AS param_set_name,
                   u.name AS owner_name, d.slug AS dataset_slug, d.name AS dataset_name
            FROM runs r
            JOIN param_versions pv ON r.param_version_id = pv.id
            JOIN param_sets ps ON pv.param_set_id = ps.id
            JOIN users u ON ps.owner_id = u.id
            JOIN datasets d ON r.dataset_id = d.id
            WHERE r.id = ?
            """,
            (cursor.lastrowid,),
        )
        row = await row_cursor.fetchone()

    return _row_to_dict(row)


@router.get("/{run_id}")
async def get_run(run_id: int):
    """Get a single run with param set and dataset info."""
    async with get_async_db() as conn:
        cursor = await conn.execute(
            """
            SELECT r.*, pv.version_number, ps.id AS param_set_id, ps.name AS param_set_name,
                   u.name AS owner_name, d.slug AS dataset_slug, d.name AS dataset_name
            FROM runs r
            JOIN param_versions pv ON r.param_version_id = pv.id
            JOIN param_sets ps ON pv.param_set_id = ps.id
            JOIN users u ON ps.owner_id = u.id
            JOIN datasets d ON r.dataset_id = d.id
            WHERE r.id = ?
            """,
            (run_id,),
        )
        row = await cursor.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Run not found")

    return _row_to_dict(row)
```

- [ ] **Step 4: Update dashboard_routes.py**

Replace `test_type` string filters with dataset joins:

```python
# server/api/dashboard_routes.py
"""Dashboard routes: summary stats and leaderboard."""
from fastapi import APIRouter

from server.db import get_async_db

router = APIRouter(prefix="/api/dashboard")


def _row_to_dict(row) -> dict:
    return dict(row)


@router.get("")
async def dashboard():
    """Return aggregate stats, best runs, recent runs, and a leaderboard."""
    async with get_async_db() as conn:
        total_cursor = await conn.execute("SELECT COUNT(*) FROM param_sets")
        total_param_sets = (await total_cursor.fetchone())[0]

        # Best runs per dataset
        ds_cursor = await conn.execute("SELECT id, slug, name FROM datasets ORDER BY id")
        datasets = await ds_cursor.fetchall()

        best_by_dataset = {}
        for ds in datasets:
            best_cursor = await conn.execute(
                """
                SELECT ps.name, pv.version_number,
                       SUM(CASE WHEN er.detected = 1 OR (er.moon_error_arcmin IS NOT NULL AND er.moon_error_arcmin < 60) THEN 1 ELSE 0 END) AS overall_pass,
                       COUNT(*) AS total,
                       CAST(SUM(CASE WHEN er.detected = 1 OR (er.moon_error_arcmin IS NOT NULL AND er.moon_error_arcmin < 60) THEN 1 ELSE 0 END) AS REAL) / COUNT(*) AS rate
                FROM runs r
                JOIN param_versions pv ON r.param_version_id = pv.id
                JOIN param_sets ps ON pv.param_set_id = ps.id
                JOIN eclipse_results er ON er.run_id = r.id
                WHERE r.dataset_id = ? AND r.status = 'done' AND r.total_eclipses > 0
                GROUP BY r.id
                ORDER BY rate DESC
                LIMIT 1
                """,
                (ds["id"],),
            )
            best_row = await best_cursor.fetchone()
            best_by_dataset[ds["slug"]] = (
                {"name": f"{best_row['name']} v{best_row['version_number']}", "rate": best_row["rate"]}
                if best_row else None
            )

        # Recent runs with overall_pass and dataset info
        recent_cursor = await conn.execute(
            """
            SELECT r.id, ps.name AS param_set_name, pv.version_number, u.name AS owner_name,
                   d.slug AS dataset_slug, d.name AS dataset_name,
                   r.status, r.total_eclipses, r.detected, r.created_at
            FROM runs r
            JOIN param_versions pv ON r.param_version_id = pv.id
            JOIN param_sets ps ON pv.param_set_id = ps.id
            JOIN users u ON ps.owner_id = u.id
            JOIN datasets d ON r.dataset_id = d.id
            ORDER BY r.created_at DESC
            LIMIT 10
            """
        )
        recent_rows = await recent_cursor.fetchall()
        recent_runs = []
        for row in recent_rows:
            d = _row_to_dict(row)
            if d["status"] == "done":
                op_cursor = await conn.execute(
                    """
                    SELECT SUM(CASE WHEN detected = 1 OR (moon_error_arcmin IS NOT NULL AND moon_error_arcmin < 60) THEN 1 ELSE 0 END) AS overall_pass
                    FROM eclipse_results WHERE run_id = ?
                    """,
                    (d["id"],),
                )
                op_row = await op_cursor.fetchone()
                d["overall_pass"] = op_row["overall_pass"] or 0
            else:
                d["overall_pass"] = None
            recent_runs.append(d)

        # Leaderboard
        leader_cursor = await conn.execute(
            """
            SELECT ps.name AS param_set_name, u.name AS owner_name,
                   AVG(
                       CAST(sub.overall_pass AS REAL) / sub.total
                   ) AS avg_rate
            FROM (
                SELECT r.id AS run_id, pv.param_set_id,
                       SUM(CASE WHEN er.detected = 1 OR (er.moon_error_arcmin IS NOT NULL AND er.moon_error_arcmin < 60) THEN 1 ELSE 0 END) AS overall_pass,
                       COUNT(*) AS total
                FROM runs r
                JOIN param_versions pv ON r.param_version_id = pv.id
                JOIN eclipse_results er ON er.run_id = r.id
                WHERE r.status = 'done' AND r.total_eclipses > 0
                GROUP BY r.id
            ) sub
            JOIN param_sets ps ON sub.param_set_id = ps.id
            JOIN users u ON ps.owner_id = u.id
            GROUP BY ps.id
            ORDER BY avg_rate DESC
            LIMIT 20
            """
        )
        leaderboard = [_row_to_dict(r) for r in await leader_cursor.fetchall()]

    return {
        "total_param_sets": total_param_sets,
        "best_solar": best_by_dataset.get("solar_eclipse"),
        "best_lunar": best_by_dataset.get("lunar_eclipse"),
        "recent_runs": recent_runs,
        "leaderboard": leaderboard,
    }
```

- [ ] **Step 5: Update results_routes.py**

Replace `jpl.test_type = r.test_type` join with `jpl.dataset_id = r.dataset_id`:

In `server/api/results_routes.py`, change line 49 from:
```python
            "SELECT id, test_type FROM runs WHERE id = ?", (run_id,)
```
to:
```python
            "SELECT id, dataset_id FROM runs WHERE id = ?", (run_id,)
```

And in the `get_result` function, change the JOIN from:
```sql
LEFT JOIN jpl_reference jpl ON jpl.julian_day_tt = er.julian_day_tt
    AND jpl.test_type = r.test_type
```
to:
```sql
LEFT JOIN jpl_reference jpl ON jpl.julian_day_tt = er.julian_day_tt
    AND jpl.dataset_id = r.dataset_id
```

And change:
```sql
SELECT er.*, r.test_type, pv.version_number,
```
to:
```sql
SELECT er.*, r.dataset_id, d.slug AS dataset_slug, d.name AS dataset_name, pv.version_number,
```

And add a JOIN:
```sql
JOIN datasets d ON r.dataset_id = d.id
```

- [ ] **Step 6: Update compare_routes.py**

Change `_get_latest_done_run` to take `dataset_id: int` instead of `test_type: str`:

```python
async def _get_latest_done_run(conn, param_set_id: int, dataset_id: int):
    """Return the latest done run for a param_set + dataset via param_versions, or None."""
    cursor = await conn.execute(
        """
        SELECT r.id, r.total_eclipses, r.detected, ps.name AS param_set_name,
               u.name AS owner_name, pv.params_json
        FROM runs r
        JOIN param_versions pv ON r.param_version_id = pv.id
        JOIN param_sets ps ON pv.param_set_id = ps.id
        JOIN users u ON ps.owner_id = u.id
        WHERE pv.param_set_id = ? AND r.dataset_id = ? AND r.status = 'done'
        ORDER BY r.completed_at DESC
        LIMIT 1
        """,
        (param_set_id, dataset_id),
    )
    return await cursor.fetchone()
```

And in the `compare` endpoint, change the `type` query param to `dataset` (slug), resolve to dataset_id:

```python
@router.get("")
async def compare(
    a: int = Query(..., description="Param set id A"),
    b: int = Query(..., description="Param set id B"),
    dataset: str = Query(default="solar_eclipse", description="Dataset slug"),
):
    """Compare latest done runs for two param sets."""
    async with get_async_db() as conn:
        ds_cursor = await conn.execute("SELECT id FROM datasets WHERE slug = ?", (dataset,))
        ds_row = await ds_cursor.fetchone()
        if ds_row is None:
            raise HTTPException(status_code=404, detail=f"Dataset '{dataset}' not found")
        dataset_id = ds_row["id"]

        run_a = await _get_latest_done_run(conn, a, dataset_id)
        # ... rest unchanged except error messages say dataset instead of type
```

- [ ] **Step 7: Update params_routes.py**

Replace all `for test_type in ("solar", "lunar"):` loops with querying datasets from DB. Key changes:

In `auto_queue_runs`:
```python
async def auto_queue_runs(conn, param_version_id: int):
    """Queue a run for each dataset for a new param version."""
    ds_rows = await (await conn.execute("SELECT id FROM datasets ORDER BY id")).fetchall()
    for ds in ds_rows:
        await conn.execute(
            "INSERT INTO runs (param_version_id, dataset_id, status) VALUES (?, ?, 'queued')",
            (param_version_id, ds["id"]),
        )
    await conn.commit()
```

In `list_param_sets` — the run query already selects `test_type`; change to join datasets:
```sql
SELECT id, dataset_id, status, total_eclipses, detected, completed_at
```

In `get_param_set` — replace `for test_type in ("solar", "lunar"):` with:
```python
ds_rows = await (await conn.execute("SELECT id, slug FROM datasets ORDER BY id")).fetchall()
for ds in ds_rows:
    # ... query with r.dataset_id = ? instead of r.test_type = ?
    item[f"{ds['slug']}_stats"] = ...
```

In `get_version` ancestor stats — same pattern:
```python
ds_rows = await (await conn.execute("SELECT id, slug FROM datasets ORDER BY id")).fetchall()
for ds in ds_rows:
    stat_cursor = await conn.execute(
        """SELECT detected, total_eclipses FROM runs
           WHERE param_version_id = ? AND dataset_id = ? AND status = 'done'
           ORDER BY completed_at DESC LIMIT 1""",
        (current_parent_id, ds["id"]),
    )
    # ...
    anc[f"{ds['slug']}_detected"] = ...
    anc[f"{ds['slug']}_total"] = ...
```

- [ ] **Step 8: Update app.py**

```python
# In server/app.py, replace:
from server.api.eclipse_routes import router as eclipse_router
# with:
from server.api.dataset_routes import router as dataset_router

# And replace:
app.include_router(eclipse_router)
# with:
app.include_router(dataset_router)
```

- [ ] **Step 9: Test the API**

```bash
source tychos_skyfield/.venv/bin/activate
PYTHONPATH=tychos_skyfield:tests:. python3 -c "
from server.db import init_db
init_db()
print('DB init OK')
"
```

Then start the server and verify endpoints:
```bash
curl http://localhost:8000/api/datasets
curl http://localhost:8000/api/datasets/summary
curl http://localhost:8000/api/datasets/solar_eclipse?page=1
curl http://localhost:8000/api/runs | python3 -m json.tool | head -20
curl http://localhost:8000/api/dashboard | python3 -m json.tool | head -30
```

- [ ] **Step 10: Commit**

```bash
git add server/api/ server/app.py
git rm server/api/eclipse_routes.py 2>/dev/null || true
git commit -m "feat: update all API routes to use dataset_id instead of test_type"
```

---

### Task 5: Update frontend — routing, sidebar, datasets pages

**Files:**
- Modify: `admin/src/App.tsx`
- Modify: `admin/src/components/sidebar.tsx`
- Create: `admin/src/pages/DatasetsPage.tsx`
- Rename/Modify: `admin/src/pages/EclipsesPage.tsx` → `admin/src/pages/DatasetDetailPage.tsx`
- Modify: `admin/src/pages/DashboardPage.tsx`
- Rename/Modify: `admin/src/components/dashboard/eclipse-datasets.tsx` → `admin/src/components/dashboard/dataset-summary.tsx`

- [ ] **Step 1: Update sidebar.tsx**

Change "Eclipses" to "Datasets" with `Database` icon, link to `/datasets`:

```tsx
// admin/src/components/sidebar.tsx
import { Link, useLocation, useNavigate } from "react-router-dom";
import {
  LayoutDashboard,
  Settings2,
  Play,
  GitCompare,
  Database,
  LogOut,
} from "lucide-react";

interface SidebarProps {
  userName: string;
  userEmail: string;
}

const navItems = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/parameters", label: "Parameters", icon: Settings2 },
  { href: "/runs", label: "Runs", icon: Play },
  { href: "/datasets", label: "Datasets", icon: Database },
  { href: "/compare", label: "Compare", icon: GitCompare },
];

// ... rest of component unchanged
```

- [ ] **Step 2: Create DatasetsPage.tsx**

```tsx
// admin/src/pages/DatasetsPage.tsx
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

interface Dataset {
  id: number;
  slug: string;
  name: string;
  event_type: string;
  source_url: string | null;
  description: string | null;
  record_count: number;
}

export default function DatasetsPage() {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    fetch("/api/datasets")
      .then((r) => r.json())
      .then((d) => {
        setDatasets(d);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  if (loading) return null;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Datasets</h1>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {datasets.map((ds) => (
          <Card
            key={ds.id}
            className="cursor-pointer transition-colors hover:bg-accent/50"
            onClick={() => navigate(`/datasets/${ds.slug}`)}
          >
            <CardHeader>
              <CardTitle className="flex items-center justify-between">
                {ds.name}
                <Badge variant="secondary" className="tabular-nums">
                  {ds.record_count} records
                </Badge>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {ds.description && (
                <p className="text-sm text-muted-foreground">{ds.description}</p>
              )}
              <div className="flex items-center gap-2">
                <Badge>{ds.event_type}</Badge>
                {ds.source_url && (
                  <a
                    href={ds.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs text-blue-500 hover:underline"
                    onClick={(e) => e.stopPropagation()}
                  >
                    Source
                  </a>
                )}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Rename EclipsesPage.tsx → DatasetDetailPage.tsx**

```bash
mv admin/src/pages/EclipsesPage.tsx admin/src/pages/DatasetDetailPage.tsx
```

Then update the file. Key changes:
- Route param is now `slug` not `type`
- Fetch from `/api/datasets/:slug` instead of `/api/eclipses/:type`
- Response includes `event_type` field to decide solar vs lunar table
- Remove the solar/lunar Tabs (each dataset is its own page now)
- Keep the catalog_type filter Select

Replace the component name and routing logic:

```tsx
// admin/src/pages/DatasetDetailPage.tsx
// Change: useParams<{ type: string }> → useParams<{ slug: string }>
// Change: fetch(`/api/eclipses/${type}?...`) → fetch(`/api/datasets/${slug}?...`)
// Change: the Tabs section removed — no more solar/lunar toggle
// Change: use response.event_type to decide SolarTable vs LunarTable
// Change: catalog type options driven by event_type
export default function DatasetDetailPage() {
  const { slug } = useParams<{ slug: string }>();
  // ... rest similar but using slug and event_type from response
```

- [ ] **Step 4: Rename eclipse-datasets.tsx → dataset-summary.tsx**

```bash
mv admin/src/components/dashboard/eclipse-datasets.tsx admin/src/components/dashboard/dataset-summary.tsx
```

Update component name and import path in DashboardPage.tsx. The component stays largely the same — cards linking to `/datasets/:slug`.

- [ ] **Step 5: Update DashboardPage.tsx**

Change import from `eclipse-datasets` to `dataset-summary`, rename component usage. Update fetch from `/api/eclipses/summary` to `/api/datasets/summary`.

- [ ] **Step 6: Update App.tsx**

```tsx
// Replace:
import EclipsesPage from "@/pages/EclipsesPage";
// With:
import DatasetsPage from "@/pages/DatasetsPage";
import DatasetDetailPage from "@/pages/DatasetDetailPage";

// Replace routes:
// <Route path="/eclipses/:type" element={<EclipsesPage />} />
// With:
// <Route path="/datasets" element={<DatasetsPage />} />
// <Route path="/datasets/:slug" element={<DatasetDetailPage />} />
```

- [ ] **Step 7: Build and verify**

```bash
cd admin && npx vite build
```

- [ ] **Step 8: Commit**

```bash
git add admin/src/
git commit -m "feat: rename eclipses UI to datasets, add datasets list page"
```

---

### Task 6: Update frontend — run table, results page, and remaining test_type references

**Files:**
- Modify: `admin/src/components/runs/run-table.tsx`
- Modify: `admin/src/pages/ResultsPage.tsx`
- Modify: `admin/src/pages/ResultDetailPage.tsx`
- Modify: `admin/src/pages/ParamDetailPage.tsx`
- Modify: `admin/src/pages/ParamVersionDetailPage.tsx`
- Modify: `admin/src/components/dashboard/recent-runs.tsx`
- Modify: `admin/src/components/compare/compare-view.tsx`

- [ ] **Step 1: Update run-table.tsx**

The API now returns `dataset_name` and `dataset_slug` instead of `test_type`. Update the mapping and the "Dataset" column:

Change the data mapping from:
```ts
testType: r.test_type,
```
to:
```ts
datasetName: r.dataset_name,
datasetSlug: r.dataset_slug,
```

Change the "Dataset" column cell from:
```tsx
{run.testType} catalog
```
to:
```tsx
{run.datasetName}
```

And the link from `/eclipses/${run.testType}` to `/datasets/${run.datasetSlug}`.

Also change the "Test Type" column to "Dataset" (remove the separate Test Type column since Dataset covers it).

- [ ] **Step 2: Update ResultsPage.tsx**

Change:
```ts
testType: runData.test_type,
```
to:
```ts
datasetName: runData.dataset_name,
datasetSlug: runData.dataset_slug,
```

And display `run.datasetName` instead of `run.testType`.

- [ ] **Step 3: Update ResultDetailPage.tsx**

Replace any reference to `test_type` in the response data with `dataset_slug` / `dataset_name`.

- [ ] **Step 4: Update ParamDetailPage.tsx**

Replace `solar_stats` / `lunar_stats` references with dynamic dataset slug keys (`solar_eclipse_stats`, `lunar_eclipse_stats`). Update UI labels accordingly.

- [ ] **Step 5: Update ParamVersionDetailPage.tsx**

Same pattern — replace `solar_detected`/`lunar_detected`/`solar_total`/`lunar_total` with `solar_eclipse_detected`/`lunar_eclipse_detected` etc. in ancestor display.

- [ ] **Step 6: Update recent-runs.tsx**

Replace `testType` display with `datasetName`.

- [ ] **Step 7: Update compare-view.tsx**

Change the `type` query param to `dataset` (slug). Update the solar/lunar toggle to use dataset slugs.

- [ ] **Step 8: Build and verify**

```bash
cd admin && npx vite build
```

- [ ] **Step 9: Commit**

```bash
git add admin/src/
git commit -m "feat: update all frontend components to use dataset_slug/dataset_name"
```

---

### Task 7: End-to-end verification

- [ ] **Step 1: Start the server and verify all pages load**

```bash
source tychos_skyfield/.venv/bin/activate
PYTHONPATH=tychos_skyfield:tests:. uvicorn server.app:app --port 8000 --reload
```

In another terminal, start the dev server:
```bash
cd admin && npm run dev
```

Verify:
- Dashboard loads with dataset summary cards
- Datasets page lists both datasets
- `/datasets/solar_eclipse` shows solar catalog with all NASA columns
- `/datasets/lunar_eclipse` shows lunar catalog with all NASA columns
- Runs page shows dataset names in the Dataset column
- Clicking a dataset link navigates correctly
- Compare page works with dataset slug

- [ ] **Step 2: Verify no test_type references remain**

```bash
grep -r "test_type" server/ --include="*.py" | grep -v __pycache__ | grep -v migrations/00[1-6]
grep -r "testType\|test_type" admin/src/ --include="*.tsx"
```

Both should return empty (only old migrations may reference test_type).

- [ ] **Step 3: Final commit**

If any fixes were needed, commit them:

```bash
git add -A
git commit -m "fix: clean up remaining test_type references"
```
