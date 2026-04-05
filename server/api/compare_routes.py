"""Compare routes: diff two param sets' eclipse results."""
from fastapi import APIRouter, HTTPException, Query

from server.db import get_async_db

router = APIRouter(prefix="/api/compare")


def _row_to_dict(row) -> dict:
    return dict(row)


async def _get_latest_done_run(conn, param_set_id: int, test_type: str):
    """Return the latest done run for a param_set + test_type via param_versions, or None."""
    cursor = await conn.execute(
        """
        SELECT r.id, r.total_eclipses, r.detected, ps.name AS param_set_name,
               u.name AS owner_name, pv.params_json
        FROM runs r
        JOIN param_versions pv ON r.param_version_id = pv.id
        JOIN param_sets ps ON pv.param_set_id = ps.id
        JOIN users u ON ps.owner_id = u.id
        WHERE pv.param_set_id = ? AND r.test_type = ? AND r.status = 'done'
        ORDER BY r.completed_at DESC
        LIMIT 1
        """,
        (param_set_id, test_type),
    )
    return await cursor.fetchone()


@router.get("")
async def compare(
    a: int = Query(..., description="Param set id A"),
    b: int = Query(..., description="Param set id B"),
    type: str = Query(default="solar", description="Test type (solar or lunar)"),
):
    """Compare latest done runs for two param sets."""
    async with get_async_db() as conn:
        run_a = await _get_latest_done_run(conn, a, type)
        if run_a is None:
            raise HTTPException(
                status_code=404,
                detail=f"No completed '{type}' run found for param_set {a}",
            )

        run_b = await _get_latest_done_run(conn, b, type)
        if run_b is None:
            raise HTTPException(
                status_code=404,
                detail=f"No completed '{type}' run found for param_set {b}",
            )

        # Fetch all eclipse results for both runs indexed by julian_day_tt + catalog_type
        cursor_a = await conn.execute(
            """
            SELECT julian_day_tt, date, catalog_type, detected, min_separation_arcmin
            FROM eclipse_results WHERE run_id = ?
            """,
            (run_a["id"],),
        )
        results_a = await cursor_a.fetchall()

        cursor_b = await conn.execute(
            """
            SELECT julian_day_tt, date, catalog_type, detected, min_separation_arcmin
            FROM eclipse_results WHERE run_id = ?
            """,
            (run_b["id"],),
        )
        results_b = await cursor_b.fetchall()

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
