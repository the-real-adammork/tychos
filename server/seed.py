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
