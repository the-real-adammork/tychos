"""Compare routes: diff two param sets' eclipse results."""
from fastapi import APIRouter, HTTPException, Query

from server.db import get_async_db

router = APIRouter(prefix="/api/compare")


def _row_to_dict(row) -> dict:
    return dict(row)


async def _get_latest_done_run(conn, param_set_id: int, dataset_id: int):
    """Return the latest done run for a param_set + dataset via param_versions, or None."""
    cursor = await conn.execute(
        """
        SELECT r.id, r.total_eclipses, ps.name AS param_set_name,
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
        if run_a is None:
            raise HTTPException(
                status_code=404,
                detail=f"No completed run found for dataset '{dataset}' and param_set {a}",
            )

        run_b = await _get_latest_done_run(conn, b, dataset_id)
        if run_b is None:
            raise HTTPException(
                status_code=404,
                detail=f"No completed run found for dataset '{dataset}' and param_set {b}",
            )

        # Fetch all eclipse results for both runs indexed by julian_day_tt + catalog_type
        cursor_a = await conn.execute(
            """
            SELECT julian_day_tt, date, catalog_type, min_separation_arcmin, tychos_error_arcmin
            FROM eclipse_results WHERE run_id = ?
            """,
            (run_a["id"],),
        )
        results_a = await cursor_a.fetchall()

        cursor_b = await conn.execute(
            """
            SELECT julian_day_tt, date, catalog_type, min_separation_arcmin, tychos_error_arcmin
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

    # Compute mean tychos error for each run
    a_errors = [r["tychos_error_arcmin"] for r in results_a if r["tychos_error_arcmin"] is not None]
    b_errors = [r["tychos_error_arcmin"] for r in results_b if r["tychos_error_arcmin"] is not None]
    run_a_mean_error = round(sum(a_errors) / len(a_errors), 2) if a_errors else None
    run_b_mean_error = round(sum(b_errors) / len(b_errors), 2) if b_errors else None

    # Find eclipses where error changed significantly
    changed = []
    all_keys = set(map_a.keys()) | set(map_b.keys())
    for key in sorted(all_keys):
        row_a = map_a.get(key)
        row_b = map_b.get(key)
        if row_a is None or row_b is None:
            continue
        err_a = row_a["tychos_error_arcmin"]
        err_b = row_b["tychos_error_arcmin"]
        if err_a is not None and err_b is not None:
            delta = err_b - err_a
            if abs(delta) > 1.0:  # Only show changes > 1 arcminute
                changed.append({
                    "date": row_a["date"],
                    "catalog_type": row_a["catalog_type"],
                    "a_error": err_a,
                    "b_error": err_b,
                    "a_sep": row_a["min_separation_arcmin"],
                    "b_sep": row_b["min_separation_arcmin"],
                    "error_delta": round(delta, 2),
                })

    return {
        "run_a": {
            "id": run_a["id"],
            "param_set_name": run_a["param_set_name"],
            "owner_name": run_a["owner_name"],
            "params_json": run_a["params_json"],
            "total_eclipses": run_a["total_eclipses"],
            "mean_tychos_error": run_a_mean_error,
        },
        "run_b": {
            "id": run_b["id"],
            "param_set_name": run_b["param_set_name"],
            "owner_name": run_b["owner_name"],
            "params_json": run_b["params_json"],
            "total_eclipses": run_b["total_eclipses"],
            "mean_tychos_error": run_b_mean_error,
        },
        "changed": changed,
    }
