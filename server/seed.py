"""Seed the database with admin user, datasets, params, and JPL reference data.

Called automatically by init_db() after migrations. Idempotent.
"""
import hashlib
import json
import os
import sqlite3
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
    _seed_predicted_reference()


def _seed_admin_user():
    """Create the initial admin user if no users exist yet.

    Requires TYCHOS_ADMIN_USER and TYCHOS_ADMIN_PASSWORD environment
    variables — there are deliberately no defaults so an unconfigured
    deploy doesn't ship with a known password. If the admin already
    exists, this is a no-op (env vars may be unset on subsequent runs).
    """
    with get_db() as conn:
        # If any user exists at all, skip seeding so we never overwrite
        # an admin and never re-prompt for env vars on every boot.
        any_user = conn.execute("SELECT id FROM users LIMIT 1").fetchone()
        if any_user:
            return

    admin_email = os.environ.get("TYCHOS_ADMIN_USER")
    admin_password = os.environ.get("TYCHOS_ADMIN_PASSWORD")
    if not admin_email or not admin_password:
        raise RuntimeError(
            "No users exist yet and TYCHOS_ADMIN_USER / TYCHOS_ADMIN_PASSWORD "
            "are not set. Set both env vars to seed the initial admin user."
        )

    with get_db() as conn:
        password_hash = bcrypt.hashpw(admin_password.encode(), bcrypt.gensalt()).decode()
        try:
            conn.execute(
                "INSERT INTO users (email, name, password_hash) VALUES (?, ?, ?)",
                (admin_email, "Admin", password_hash),
            )
            conn.commit()
            print(f"[seed] Created admin user ({admin_email})")
        except sqlite3.IntegrityError:
            # Another process (e.g. the worker started in parallel) raced us
            # and inserted the admin first. That's fine — the seed is meant
            # to be idempotent.
            pass


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
        # Assign ownership to whichever user was seeded first (the admin).
        # If no users exist yet, skip — _seed_admin_user runs before this.
        user = conn.execute("SELECT id FROM users ORDER BY id LIMIT 1").fetchone()
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

    Populates (or backfills best_jd on) jpl_reference. If every row already has
    a best_jd this is a no-op; otherwise it computes values only for the rows
    that need them.
    """
    with get_db() as conn:
        total = conn.execute("SELECT COUNT(*) FROM jpl_reference").fetchone()[0]
        missing_best = conn.execute(
            "SELECT COUNT(*) FROM jpl_reference WHERE best_jd IS NULL"
        ).fetchone()[0]
        missing_best_pos = conn.execute(
            "SELECT COUNT(*) FROM jpl_reference WHERE best_jd IS NOT NULL AND sun_ra_at_best_rad IS NULL"
        ).fetchone()[0]

    if total > 0 and missing_best == 0 and missing_best_pos == 0:
        return

    if total > 0 and missing_best > 0:
        _backfill_jpl_best_jd(missing_best)

    if total > 0 and missing_best_pos > 0:
        _backfill_jpl_best_positions(missing_best_pos)

    if total > 0:
        return

    print("[seed] Computing JPL reference positions (this takes a moment)...")

    from server.services.jpl_scanner import scan_jpl_eclipses

    rows = []
    with get_db() as conn:
        datasets = _get_all_datasets(conn)
        for ds in datasets:
            is_lunar = ds["slug"] == "lunar_eclipse"
            eclipses = conn.execute(
                "SELECT julian_day_tt FROM eclipse_catalog WHERE dataset_id = ? ORDER BY julian_day_tt",
                (ds["id"],),
            ).fetchall()

            jpl_rows = scan_jpl_eclipses(
                [{"julian_day_tt": e["julian_day_tt"]} for e in eclipses],
                "de440s.bsp",
                is_lunar=is_lunar,
            )

            for r in jpl_rows:
                rows.append((
                    ds["id"],
                    r["julian_day_tt"],
                    r["sun_ra_rad"],
                    r["sun_dec_rad"],
                    r["moon_ra_rad"],
                    r["moon_dec_rad"],
                    r["separation_arcmin"],
                    r["moon_ra_vel"],
                    r["moon_dec_vel"],
                    r["best_jd"],
                    r["sun_ra_at_best_rad"],
                    r["sun_dec_at_best_rad"],
                    r["moon_ra_at_best_rad"],
                    r["moon_dec_at_best_rad"],
                ))

    with get_db() as conn:
        conn.executemany(
            """INSERT OR IGNORE INTO jpl_reference
               (dataset_id, julian_day_tt, sun_ra_rad, sun_dec_rad, moon_ra_rad, moon_dec_rad,
                separation_arcmin, moon_ra_vel, moon_dec_vel, best_jd,
                sun_ra_at_best_rad, sun_dec_at_best_rad, moon_ra_at_best_rad, moon_dec_at_best_rad)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        conn.commit()

    print(f"[seed] Computed {len(rows)} JPL reference positions")


def _backfill_jpl_best_jd(missing_count: int) -> None:
    """Populate best_jd on existing jpl_reference rows that are missing it."""
    print(f"[seed] Backfilling JPL best_jd for {missing_count} rows...")

    from skyfield.api import load as skyfield_load
    from server.services.jpl_scanner import _scan_jpl_min_jd

    eph = skyfield_load("de440s.bsp")
    ts = skyfield_load.timescale()
    earth = eph["earth"]

    with get_db() as conn:
        rows = conn.execute(
            """SELECT j.id, j.julian_day_tt, d.slug
                 FROM jpl_reference j
                 JOIN datasets d ON j.dataset_id = d.id
                WHERE j.best_jd IS NULL""",
        ).fetchall()

    updates = []
    for row in rows:
        is_lunar = row["slug"] == "lunar_eclipse"
        best_jd = _scan_jpl_min_jd(earth, eph, ts, row["julian_day_tt"], is_lunar)
        updates.append((best_jd, row["id"]))

    with get_db() as conn:
        conn.executemany(
            "UPDATE jpl_reference SET best_jd = ? WHERE id = ?",
            updates,
        )
        conn.commit()

    print(f"[seed] Backfilled {len(updates)} JPL best_jd values")


def _backfill_jpl_best_positions(missing_count: int) -> None:
    """Populate Sun/Moon positions at best_jd on existing jpl_reference rows."""
    print(f"[seed] Backfilling JPL positions at best_jd for {missing_count} rows...")

    from skyfield.api import load as skyfield_load

    eph = skyfield_load("de440s.bsp")
    ts = skyfield_load.timescale()
    earth = eph["earth"]

    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, best_jd FROM jpl_reference WHERE best_jd IS NOT NULL AND sun_ra_at_best_rad IS NULL",
        ).fetchall()

    updates = []
    for row in rows:
        t = ts.tt_jd(row["best_jd"])
        s_ra, s_dec, _ = earth.at(t).observe(eph["sun"]).radec()
        m_ra, m_dec, _ = earth.at(t).observe(eph["moon"]).radec()
        updates.append((
            float(s_ra.radians), float(s_dec.radians),
            float(m_ra.radians), float(m_dec.radians),
            row["id"],
        ))

    with get_db() as conn:
        conn.executemany(
            """UPDATE jpl_reference
               SET sun_ra_at_best_rad = ?, sun_dec_at_best_rad = ?,
                   moon_ra_at_best_rad = ?, moon_dec_at_best_rad = ?
             WHERE id = ?""",
            updates,
        )
        conn.commit()

    print(f"[seed] Backfilled {len(updates)} JPL best-position values")


def _seed_predicted_reference():
    """Precompute predicted eclipse geometry from catalog data.

    Uses only catalog parameters (gamma, magnitude) — no Skyfield, no Tychos.
    Only runs once — skips if predicted_reference table already has data.
    """
    with get_db() as conn:
        count = conn.execute("SELECT COUNT(*) FROM predicted_reference").fetchone()[0]
        if count > 0:
            return

    print("[seed] Computing predicted reference geometry from catalog data...")

    from server.services.predicted_geometry import (
        expected_separation_from_gamma,
        solar_disk_radii,
        lunar_shadow_radii,
        approach_angle_from_gamma,
    )

    rows = []

    # Solar eclipses
    solar_path = DATA_DIR / "solar_eclipses.json"
    with open(solar_path) as f:
        solar_eclipses = json.load(f)

    for ecl in solar_eclipses:
        sep = expected_separation_from_gamma(ecl["gamma"])
        moon_r, sun_r = solar_disk_radii(ecl["magnitude"], ecl.get("type", "central"))
        angle = approach_angle_from_gamma(ecl["gamma"])
        rows.append((
            ecl["julian_day_tt"], "solar",
            round(sep, 4), round(moon_r, 4), round(sun_r, 4),
            None, None,
            round(angle, 2), ecl["gamma"], ecl["magnitude"],
        ))

    # Lunar eclipses
    lunar_path = DATA_DIR / "lunar_eclipses.json"
    with open(lunar_path) as f:
        lunar_eclipses = json.load(f)

    for ecl in lunar_eclipses:
        sep = expected_separation_from_gamma(ecl["gamma"])
        umbra_r, penumbra_r, moon_r = lunar_shadow_radii(
            ecl["um_mag"], ecl["pen_mag"], ecl["gamma"]
        )
        angle = approach_angle_from_gamma(ecl["gamma"])
        rows.append((
            ecl["julian_day_tt"], "lunar",
            round(sep, 4), round(moon_r, 4), None,
            round(umbra_r, 4), round(penumbra_r, 4),
            round(angle, 2), ecl["gamma"], ecl["pen_mag"],
        ))

    with get_db() as conn:
        conn.executemany(
            """INSERT OR IGNORE INTO predicted_reference
               (julian_day_tt, test_type, expected_separation_arcmin,
                moon_apparent_radius_arcmin, sun_apparent_radius_arcmin,
                umbra_radius_arcmin, penumbra_radius_arcmin,
                approach_angle_deg, gamma, catalog_magnitude)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        conn.commit()

    print(f"[seed] Computed {len(rows)} predicted reference geometries")
