"""One-time export of eclipse scanner goldens for v1-original/v1.

Reads the completed v1-original/v1 runs for both solar and lunar datasets
from the local SQLite DB and writes four JSON goldens to
tests/data/goldens/. Safe to re-run; overwrites existing files.

Usage:
    python scripts/export_eclipse_goldens.py
"""
import json
import sys
from pathlib import Path

# Make server package importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from server.db import get_db

REPO_ROOT = Path(__file__).parent.parent
GOLDENS_DIR = REPO_ROOT / "tests" / "data" / "goldens"

# Column projection: only the fields scan_solar_eclipses / scan_lunar_eclipses
# return. Enrichment columns (tychos_error_arcmin, jpl_error_arcmin,
# jpl_timing_offset_min, moon_error_arcmin) are intentionally excluded.
TYCHOS_COLUMNS = [
    "julian_day_tt",
    "date",
    "catalog_type",
    "magnitude",
    "detected",
    "threshold_arcmin",
    "min_separation_arcmin",
    "timing_offset_min",
    "best_jd",
    "sun_ra_rad",
    "sun_dec_rad",
    "moon_ra_rad",
    "moon_dec_rad",
    "moon_ra_vel",
    "moon_dec_vel",
]

# jpl_reference projection: everything except id and dataset_id.
JPL_COLUMNS = [
    "julian_day_tt",
    "sun_ra_rad",
    "sun_dec_rad",
    "moon_ra_rad",
    "moon_dec_rad",
    "separation_arcmin",
    "moon_ra_vel",
    "moon_dec_vel",
    "best_jd",
]

DATASETS = [
    ("solar_eclipse", "solar"),
    ("lunar_eclipse", "lunar"),
]


def _resolve_run_id(conn, dataset_slug: str) -> int:
    row = conn.execute(
        """
        SELECT r.id, r.status
          FROM runs r
          JOIN param_versions pv ON r.param_version_id = pv.id
          JOIN param_sets ps ON pv.param_set_id = ps.id
          JOIN datasets d ON r.dataset_id = d.id
         WHERE ps.name = 'v1-original'
           AND pv.version_number = 1
           AND d.slug = ?
         ORDER BY r.id DESC
         LIMIT 1
        """,
        (dataset_slug,),
    ).fetchone()
    if row is None:
        raise SystemExit(
            f"No run found for v1-original/v1 dataset={dataset_slug}. "
            f"Run the scanner for this dataset first."
        )
    if row["status"] != "done":
        raise SystemExit(
            f"Run {row['id']} (v1-original/v1 {dataset_slug}) has status "
            f"{row['status']!r}, expected 'done'."
        )
    return row["id"]


def _resolve_dataset_id(conn, dataset_slug: str) -> int:
    row = conn.execute(
        "SELECT id FROM datasets WHERE slug = ?",
        (dataset_slug,),
    ).fetchone()
    if row is None:
        raise SystemExit(f"Dataset {dataset_slug!r} not found")
    return row["id"]


def _export_tychos(conn, run_id: int) -> list[dict]:
    cols = ", ".join(TYCHOS_COLUMNS)
    rows = conn.execute(
        f"SELECT {cols} FROM eclipse_results WHERE run_id = ? ORDER BY julian_day_tt",
        (run_id,),
    ).fetchall()
    return [{c: r[c] for c in TYCHOS_COLUMNS} for r in rows]


def _export_jpl(conn, dataset_id: int) -> list[dict]:
    cols = ", ".join(JPL_COLUMNS)
    rows = conn.execute(
        f"SELECT {cols} FROM jpl_reference WHERE dataset_id = ? ORDER BY julian_day_tt",
        (dataset_id,),
    ).fetchall()
    return [{c: r[c] for c in JPL_COLUMNS} for r in rows]


def _write_json(path: Path, data: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")


def main() -> None:
    GOLDENS_DIR.mkdir(parents=True, exist_ok=True)

    with get_db() as conn:
        for slug, short in DATASETS:
            run_id = _resolve_run_id(conn, slug)
            dataset_id = _resolve_dataset_id(conn, slug)

            tychos_rows = _export_tychos(conn, run_id)
            jpl_rows = _export_jpl(conn, dataset_id)

            tychos_path = GOLDENS_DIR / f"{short}_tychos_v1.json"
            jpl_path = GOLDENS_DIR / f"{short}_jpl_v1.json"

            _write_json(tychos_path, tychos_rows)
            _write_json(jpl_path, jpl_rows)

            print(f"[export] {slug}: {len(tychos_rows)} tychos rows -> {tychos_path.relative_to(REPO_ROOT)}")
            print(f"[export] {slug}: {len(jpl_rows)} jpl rows    -> {jpl_path.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
