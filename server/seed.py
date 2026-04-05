"""Seed the database with an admin user and v1-original parameter set.

Called automatically by init_db() after migrations. Idempotent.
"""
import hashlib
import json
from pathlib import Path

import bcrypt

from server.db import get_db

PARAMS_PATH = Path(__file__).parent.parent / "params" / "v1-original.json"


def seed():
    with get_db() as conn:
        # Admin user
        existing = conn.execute("SELECT id FROM users WHERE email = ?", ("admin@tychos.local",)).fetchone()
        if existing:
            user_id = existing["id"]
        else:
            password_hash = bcrypt.hashpw(b"admin", bcrypt.gensalt()).decode()
            cur = conn.execute(
                "INSERT INTO users (email, name, password_hash) VALUES (?, ?, ?)",
                ("admin@tychos.local", "Admin", password_hash),
            )
            user_id = cur.lastrowid
            conn.commit()
            print("[seed] Created admin user (admin@tychos.local / admin)")

        # v1-original param set
        existing_ps = conn.execute("SELECT id FROM param_sets WHERE name = ?", ("v1-original",)).fetchone()
        if existing_ps:
            return

        params_json = PARAMS_PATH.read_text()
        params_md5 = hashlib.md5(json.dumps(json.loads(params_json), sort_keys=True).encode()).hexdigest()

        cur = conn.execute(
            "INSERT INTO param_sets (name, owner_id) VALUES (?, ?)",
            ("v1-original", user_id),
        )
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
