"""Seed the database with an admin user, v1-original params, and JPL reference data.

Called automatically by init_db() after migrations. Idempotent.
"""
import hashlib
import json
import sys
from pathlib import Path

import bcrypt
import numpy as np

from server.db import get_db

PARAMS_PATH = Path(__file__).parent.parent / "params" / "v1-original.json"
DATA_DIR = Path(__file__).parent.parent / "tests" / "data"

# Add paths for helpers
sys.path.insert(0, str(Path(__file__).parent.parent / "tychos_skyfield"))
sys.path.insert(0, str(Path(__file__).parent.parent / "tests"))


def seed():
    _seed_admin_user()
    _seed_v1_original()
    _seed_jpl_reference()


def _seed_admin_user():
    with get_db() as conn:
        existing = conn.execute("SELECT id FROM users WHERE email = ?", ("admin@tychos.local",)).fetchone()
        if existing:
            return
        password_hash = bcrypt.hashpw(b"admin", bcrypt.gensalt()).decode()
        conn.execute(
            "INSERT INTO users (email, name, password_hash) VALUES (?, ?, ?)",
            ("admin@tychos.local", "Admin", password_hash),
        )
        conn.commit()
        print("[seed] Created admin user (admin@tychos.local / admin)")


def _seed_v1_original():
    with get_db() as conn:
        existing = conn.execute("SELECT id FROM param_sets WHERE name = ?", ("v1-original",)).fetchone()
        if existing:
            return

        user = conn.execute("SELECT id FROM users WHERE email = ?", ("admin@tychos.local",)).fetchone()
        params_json = PARAMS_PATH.read_text()
        params_md5 = hashlib.md5(json.dumps(json.loads(params_json), sort_keys=True).encode()).hexdigest()

        cur = conn.execute("INSERT INTO param_sets (name, owner_id) VALUES (?, ?)", ("v1-original", user["id"]))
        param_set_id = cur.lastrowid

        cur = conn.execute(
            "INSERT INTO param_versions (param_set_id, version_number, params_md5, params_json) VALUES (?, 1, ?, ?)",
            (param_set_id, params_md5, params_json),
        )
        param_version_id = cur.lastrowid

        for test_type in ("solar", "lunar"):
            conn.execute(
                "INSERT INTO runs (param_version_id, test_type, status) VALUES (?, ?, 'queued')",
                (param_version_id, test_type),
            )
        conn.commit()
        print("[seed] Created v1-original param set with 2 queued runs")


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
    for test_type in ("solar", "lunar"):
        catalog_path = DATA_DIR / f"{test_type}_eclipses.json"
        with open(catalog_path) as f:
            eclipses = json.load(f)

        for ecl in eclipses:
            jd = ecl["julian_day_tt"]
            t = ts.tt_jd(jd)

            sun_ra, sun_dec, _ = earth.at(t).observe(eph["sun"]).radec()
            moon_ra, moon_dec, _ = earth.at(t).observe(eph["moon"]).radec()

            s_ra, s_dec = sun_ra.radians, sun_dec.radians
            m_ra, m_dec = moon_ra.radians, moon_dec.radians
            sep = float(np.degrees(angular_separation(s_ra, s_dec, m_ra, m_dec)) * 60)

            rows.append((jd, test_type, float(s_ra), float(s_dec), float(m_ra), float(m_dec), round(sep, 2)))

    with get_db() as conn:
        conn.executemany(
            """INSERT OR IGNORE INTO jpl_reference
               (julian_day_tt, test_type, sun_ra_rad, sun_dec_rad, moon_ra_rad, moon_dec_rad, separation_arcmin)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        conn.commit()

    print(f"[seed] Computed {len(rows)} JPL reference positions")
