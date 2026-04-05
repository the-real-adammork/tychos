"""Compare routes: diff two param sets' eclipse results."""
from fastapi import APIRouter, HTTPException, Query

from server.db import get_db

router = APIRouter(prefix="/api/compare")


def _row_to_dict(row) -> dict:
    return dict(row)


def _get_latest_done_run(conn, param_set_id: int, test_type: str):
    """Return the latest done run for a param_set + test_type, or None."""
    return conn.execute(
        """
        SELECT r.id, r.total_eclipses, r.detected, p.name AS param_set_name, u.name AS owner_name,
               p.params_json
        FROM runs r
        JOIN param_sets p ON r.param_set_id = p.id
        JOIN users u ON p.owner_id = u.id
        WHERE r.param_set_id = ? AND r.test_type = ? AND r.status = 'done'
        ORDER BY r.completed_at DESC
        LIMIT 1
        """,
        (param_set_id, test_type),
    ).fetchone()


@router.get("")
def compare(
    a: int = Query(..., description="Param set id A"),
    b: int = Query(..., description="Param set id B"),
    type: str = Query(default="solar", description="Test type (solar or lunar)"),
):
    """Compare latest done runs for two param sets."""
    with get_db() as conn:
        run_a = _get_latest_done_run(conn, a, type)
        if run_a is None:
            raise HTTPException(
                status_code=404,
                detail=f"No completed '{type}' run found for param_set {a}",
            )

        run_b = _get_latest_done_run(conn, b, type)
        if run_b is None:
            raise HTTPException(
                status_code=404,
                detail=f"No completed '{type}' run found for param_set {b}",
            )

        # Fetch all eclipse results for both runs indexed by julian_day_tt + catalog_type
        results_a = conn.execute(
            """
            SELECT julian_day_tt, date, catalog_type, detected, min_separation_arcmin
            FROM eclipse_results WHERE run_id = ?
            """,
            (run_a["id"],),
        ).fetchall()

        results_b = conn.execute(
            """
            SELECT julian_day_tt, date, catalog_type, detected, min_separation_arcmin
            FROM eclipse_results WHERE run_id = ?
            """,
            (run_b["id"],),
        ).fetchall()

    # Build lookup maps keyed by (julian_day_tt, catalog_type)
    map_a = {
        (r["julian_day_tt"], r["catalog_type"]): r for r in results_a
    }
    map_b = {
        (r["julian_day_tt"], r["catalog_type"]): r for r in results_b
    }

    # Find eclipses where detected status differs
    changed = []
    all_keys = set(map_a.keys()) | set(map_b.keys())
    for key in sorted(all_keys):
        row_a = map_a.get(key)
        row_b = map_b.get(key)
        if row_a is None or row_b is None:
            continue
        if bool(row_a["detected"]) != bool(row_b["detected"]):
            changed.append(
                {
                    "date": row_a["date"],
                    "catalog_type": row_a["catalog_type"],
                    "a_detected": bool(row_a["detected"]),
                    "b_detected": bool(row_b["detected"]),
                    "a_sep": row_a["min_separation_arcmin"],
                    "b_sep": row_b["min_separation_arcmin"],
                }
            )

    return {
        "run_a": {
            "id": run_a["id"],
            "param_set_name": run_a["param_set_name"],
            "owner_name": run_a["owner_name"],
            "params_json": run_a["params_json"],
            "total_eclipses": run_a["total_eclipses"],
            "detected": run_a["detected"],
        },
        "run_b": {
            "id": run_b["id"],
            "param_set_name": run_b["param_set_name"],
            "owner_name": run_b["owner_name"],
            "params_json": run_b["params_json"],
            "total_eclipses": run_b["total_eclipses"],
            "detected": run_b["detected"],
        },
        "changed": changed,
    }
