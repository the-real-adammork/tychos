"""
SQLite database module for Tychos eclipse test results.
"""
import hashlib
import json
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "results" / "tychos_results.db"
PARAMS_DIR = Path(__file__).parent.parent / "params"
REPO_ROOT = Path(__file__).parent.parent

CODE_VERSION = "1.0"

SCHEMA = """
CREATE TABLE IF NOT EXISTS param_sets (
    param_set_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL UNIQUE,
    params_md5    TEXT NOT NULL,
    params_json   TEXT NOT NULL,
    created_date  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    run_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    param_set_id   INTEGER NOT NULL REFERENCES param_sets(param_set_id),
    params_name    TEXT NOT NULL,
    test_type      TEXT NOT NULL,
    code_version   TEXT NOT NULL,
    run_date       TEXT NOT NULL,
    tsn_commit     TEXT,
    tychos_skyfield_commit TEXT,
    total_eclipses INTEGER NOT NULL,
    detected       INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS eclipse_results (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id                INTEGER NOT NULL REFERENCES runs(run_id),
    julian_day_tt         REAL NOT NULL,
    date                  TEXT NOT NULL,
    catalog_type          TEXT NOT NULL,
    magnitude             REAL NOT NULL,
    detected              INTEGER NOT NULL,
    threshold_arcmin      REAL NOT NULL,
    min_separation_arcmin REAL,
    timing_offset_min     REAL,
    best_jd               REAL,
    sun_ra_rad            REAL,
    sun_dec_rad           REAL,
    moon_ra_rad           REAL,
    moon_dec_rad          REAL
);
"""


def canonical_md5(params_dict):
    """Compute MD5 of canonical JSON representation."""
    canonical = json.dumps(params_dict, sort_keys=True).encode()
    return hashlib.md5(canonical).hexdigest()


def get_submodule_commit(submodule_path):
    """Get the current HEAD commit hash of a submodule."""
    full_path = REPO_ROOT / submodule_path
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=full_path, capture_output=True, text=True, check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def init_db():
    """Create or open the database and ensure schema exists."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript(SCHEMA)
    return conn


def sync_param_sets(conn):
    """Load all JSON files from params/ into the param_sets table.

    - New files (by name): inserted
    - Changed files (same name, different md5): updated
    - Renamed files (same md5, different name): name updated
    """
    if not PARAMS_DIR.exists():
        return

    for path in sorted(PARAMS_DIR.glob("*.json")):
        name = path.stem
        with open(path) as f:
            params = json.load(f)
        md5 = canonical_md5(params)
        params_json = json.dumps(params, sort_keys=True)
        now = datetime.now(timezone.utc).isoformat()

        # Check if this md5 already exists under a different name
        row = conn.execute(
            "SELECT param_set_id, name FROM param_sets WHERE params_md5 = ?", (md5,)
        ).fetchone()
        if row:
            if row[1] != name:
                conn.execute(
                    "UPDATE param_sets SET name = ? WHERE param_set_id = ?",
                    (name, row[0]),
                )
            continue

        # Check if this name exists with different content
        row = conn.execute(
            "SELECT param_set_id FROM param_sets WHERE name = ?", (name,)
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE param_sets SET params_md5 = ?, params_json = ?, created_date = ? "
                "WHERE param_set_id = ?",
                (md5, params_json, now, row[0]),
            )
            continue

        # New param set
        conn.execute(
            "INSERT INTO param_sets (name, params_md5, params_json, created_date) "
            "VALUES (?, ?, ?, ?)",
            (name, md5, params_json, now),
        )

    conn.commit()


def run_exists(conn, params_md5, test_type):
    """Check if a run with this params_md5 + test_type + code_version already exists."""
    row = conn.execute(
        "SELECT 1 FROM runs r JOIN param_sets p ON r.param_set_id = p.param_set_id "
        "WHERE p.params_md5 = ? AND r.test_type = ? AND r.code_version = ?",
        (params_md5, test_type, CODE_VERSION),
    ).fetchone()
    return row is not None


def insert_run(conn, param_set_id, params_name, test_type, total_eclipses,
               detected, eclipse_rows):
    """Insert a complete run with all eclipse results in one transaction.

    eclipse_rows is a list of dicts with keys matching the eclipse_results columns
    (excluding id and run_id).
    """
    now = datetime.now(timezone.utc).isoformat()
    tsn_commit = get_submodule_commit("TSN")
    ts_commit = get_submodule_commit("tychos_skyfield")

    cur = conn.execute(
        "INSERT INTO runs (param_set_id, params_name, test_type, code_version, "
        "run_date, tsn_commit, tychos_skyfield_commit, total_eclipses, detected) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (param_set_id, params_name, test_type, CODE_VERSION, now,
         tsn_commit, ts_commit, total_eclipses, detected),
    )
    run_id = cur.lastrowid

    conn.executemany(
        "INSERT INTO eclipse_results (run_id, julian_day_tt, date, catalog_type, "
        "magnitude, detected, threshold_arcmin, min_separation_arcmin, "
        "timing_offset_min, best_jd, sun_ra_rad, sun_dec_rad, moon_ra_rad, moon_dec_rad) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [(run_id, r["julian_day_tt"], r["date"], r["catalog_type"],
          r["magnitude"], r["detected"], r["threshold_arcmin"],
          r["min_separation_arcmin"], r["timing_offset_min"], r["best_jd"],
          r["sun_ra_rad"], r["sun_dec_rad"], r["moon_ra_rad"], r["moon_dec_rad"])
         for r in eclipse_rows],
    )

    conn.commit()
    return run_id


def get_param_set(conn, name):
    """Get a param_set row by name. Returns (param_set_id, name, params_md5, params_json) or None."""
    return conn.execute(
        "SELECT param_set_id, name, params_md5, params_json FROM param_sets WHERE name = ?",
        (name,),
    ).fetchone()
