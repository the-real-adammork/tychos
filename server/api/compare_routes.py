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


async def _saros_groups_for_run(conn, run_id: int, dataset_id: int) -> list[dict]:
    """Compute Saros groups for a run by joining results with the catalog."""
    cursor = await conn.execute(
        """
        SELECT
            ec.saros_num,
            COUNT(*) AS count,
            MIN(SUBSTR(er.date, 1, 4)) AS year_start,
            MAX(SUBSTR(er.date, 1, 4)) AS year_end,
            AVG(er.tychos_error_arcmin) AS mean_tychos_error,
            AVG(er.jpl_error_arcmin) AS mean_jpl_error
        FROM eclipse_results er
        JOIN eclipse_catalog ec ON ec.julian_day_tt = er.julian_day_tt AND ec.dataset_id = ?
        WHERE er.run_id = ? AND ec.saros_num IS NOT NULL
        GROUP BY ec.saros_num
        ORDER BY ec.saros_num
        """,
        (dataset_id, run_id),
    )
    rows = await cursor.fetchall()
    out = []
    for r in rows:
        d = dict(r)
        for k in ("mean_tychos_error", "mean_jpl_error"):
            if d[k] is not None:
                d[k] = round(d[k], 2)
        out.append(d)
    return out


@router.get("/saros")
async def compare_saros(
    a: int = Query(..., description="Param set id A (primary)"),
    b: int | None = Query(default=None, description="Param set id B (optional comparison)"),
    dataset: str = Query(default="solar_eclipse", description="Dataset slug"),
):
    """Saros-grouped error comparison.

    If `b` is omitted, returns Saros groups for A only (single-run analysis).
    If `b` is given, returns groups from both runs joined by saros_num with delta.
    """
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

        groups_a = await _saros_groups_for_run(conn, run_a["id"], dataset_id)

        if b is None:
            return {
                "run_a": {
                    "id": run_a["id"],
                    "param_set_name": run_a["param_set_name"],
                    "owner_name": run_a["owner_name"],
                },
                "run_b": None,
                "groups": [
                    {**g, "a_mean_tychos_error": g["mean_tychos_error"]}
                    for g in groups_a
                ],
            }

        run_b = await _get_latest_done_run(conn, b, dataset_id)
        if run_b is None:
            raise HTTPException(
                status_code=404,
                detail=f"No completed run found for dataset '{dataset}' and param_set {b}",
            )

        groups_b = await _saros_groups_for_run(conn, run_b["id"], dataset_id)
        b_by_saros = {g["saros_num"]: g for g in groups_b}

        merged = []
        for ga in groups_a:
            saros = ga["saros_num"]
            gb = b_by_saros.get(saros)
            a_err = ga["mean_tychos_error"]
            b_err = gb["mean_tychos_error"] if gb else None
            delta = (
                round(b_err - a_err, 2)
                if a_err is not None and b_err is not None
                else None
            )
            merged.append({
                "saros_num": saros,
                "count": ga["count"],
                "year_start": ga["year_start"],
                "year_end": ga["year_end"],
                "a_mean_tychos_error": a_err,
                "b_mean_tychos_error": b_err,
                "delta": delta,
            })

        return {
            "run_a": {
                "id": run_a["id"],
                "param_set_name": run_a["param_set_name"],
                "owner_name": run_a["owner_name"],
            },
            "run_b": {
                "id": run_b["id"],
                "param_set_name": run_b["param_set_name"],
                "owner_name": run_b["owner_name"],
            },
            "groups": merged,
        }
