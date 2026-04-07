"""Eclipse results routes: paginated list per run with error metrics."""
from fastapi import APIRouter, HTTPException, Query

from server.db import get_async_db

router = APIRouter(prefix="/api/results")

PAGE_SIZE = 50


@router.get("/{run_id}")
async def list_results(
    run_id: int,
    page: int = Query(default=1, ge=1),
    catalog_type: str | None = Query(default=None),
    min_tychos_error: float | None = Query(default=None),
    max_tychos_error: float | None = Query(default=None),
):
    """Paginated eclipse results for a run with error metrics."""
    async with get_async_db() as conn:
        run_cursor = await conn.execute(
            "SELECT id, dataset_id FROM runs WHERE id = ?", (run_id,)
        )
        run_row = await run_cursor.fetchone()
        if run_row is None:
            raise HTTPException(status_code=404, detail="Run not found")

        conditions = ["er.run_id = ?"]
        values: list = [run_id]

        if catalog_type is not None:
            conditions.append("er.catalog_type = ?")
            values.append(catalog_type)

        if min_tychos_error is not None:
            conditions.append("er.tychos_error_arcmin >= ?")
            values.append(min_tychos_error)

        if max_tychos_error is not None:
            conditions.append("er.tychos_error_arcmin <= ?")
            values.append(max_tychos_error)

        where_clause = "WHERE " + " AND ".join(conditions)

        # Total count with filters
        total_cursor = await conn.execute(
            f"SELECT COUNT(*) FROM eclipse_results er {where_clause}", values
        )
        total = (await total_cursor.fetchone())[0]

        # Stats for full run (unfiltered)
        stats_cursor = await conn.execute(
            """
            SELECT
                COUNT(*) AS total,
                AVG(tychos_error_arcmin) AS mean_tychos_error,
                AVG(jpl_error_arcmin) AS mean_jpl_error,
                MAX(tychos_error_arcmin) AS max_tychos_error,
                MAX(jpl_error_arcmin) AS max_jpl_error
            FROM eclipse_results
            WHERE run_id = ?
            """,
            (run_id,),
        )
        s = await stats_cursor.fetchone()

        # Median (SQLite doesn't have MEDIAN, compute in Python)
        median_cursor = await conn.execute(
            "SELECT tychos_error_arcmin, jpl_error_arcmin FROM eclipse_results WHERE run_id = ? ORDER BY tychos_error_arcmin",
            (run_id,),
        )
        all_errors = await median_cursor.fetchall()
        tychos_errors = [r["tychos_error_arcmin"] for r in all_errors if r["tychos_error_arcmin"] is not None]
        jpl_errors = [r["jpl_error_arcmin"] for r in all_errors if r["jpl_error_arcmin"] is not None]

        def median(vals):
            if not vals:
                return None
            vals = sorted(vals)
            n = len(vals)
            if n % 2 == 0:
                return (vals[n // 2 - 1] + vals[n // 2]) / 2
            return vals[n // 2]

        # Paginated results
        offset = (page - 1) * PAGE_SIZE
        rows_cursor = await conn.execute(
            f"""
            SELECT er.*
            FROM eclipse_results er
            {where_clause}
            ORDER BY er.julian_day_tt ASC
            LIMIT ? OFFSET ?
            """,
            values + [PAGE_SIZE, offset],
        )
        rows = await rows_cursor.fetchall()

    return {
        "results": [dict(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": PAGE_SIZE,
        "stats": {
            "total": s["total"] or 0,
            "mean_tychos_error": round(s["mean_tychos_error"], 2) if s["mean_tychos_error"] else None,
            "mean_jpl_error": round(s["mean_jpl_error"], 2) if s["mean_jpl_error"] else None,
            "median_tychos_error": round(median(tychos_errors), 2) if tychos_errors else None,
            "median_jpl_error": round(median(jpl_errors), 2) if jpl_errors else None,
            "max_tychos_error": round(s["max_tychos_error"], 2) if s["max_tychos_error"] else None,
            "max_jpl_error": round(s["max_jpl_error"], 2) if s["max_jpl_error"] else None,
        },
    }


@router.get("/{run_id}/{result_id}")
async def get_result(run_id: int, result_id: int):
    """Get a single eclipse result with run context, JPL and predicted reference data."""
    async with get_async_db() as conn:
        cursor = await conn.execute(
            """
            SELECT er.*, r.dataset_id, d.slug AS dataset_slug, d.name AS dataset_name,
                   REPLACE(d.slug, '_eclipse', '') AS test_type, pv.version_number,
                   ps.id AS param_set_id, ps.name AS param_set_name,
                   jpl.sun_ra_rad AS jpl_sun_ra_rad, jpl.sun_dec_rad AS jpl_sun_dec_rad,
                   jpl.moon_ra_rad AS jpl_moon_ra_rad, jpl.moon_dec_rad AS jpl_moon_dec_rad,
                   jpl.separation_arcmin AS jpl_separation_arcmin,
                   jpl.moon_ra_vel AS jpl_moon_ra_vel, jpl.moon_dec_vel AS jpl_moon_dec_vel,
                   pred.expected_separation_arcmin,
                   pred.moon_apparent_radius_arcmin,
                   pred.sun_apparent_radius_arcmin,
                   pred.umbra_radius_arcmin,
                   pred.penumbra_radius_arcmin,
                   pred.approach_angle_deg,
                   pred.gamma AS pred_gamma,
                   pred.catalog_magnitude AS pred_catalog_magnitude
            FROM eclipse_results er
            JOIN runs r ON er.run_id = r.id
            JOIN datasets d ON r.dataset_id = d.id
            JOIN param_versions pv ON r.param_version_id = pv.id
            JOIN param_sets ps ON pv.param_set_id = ps.id
            LEFT JOIN jpl_reference jpl ON jpl.julian_day_tt = er.julian_day_tt
                AND jpl.dataset_id = r.dataset_id
            LEFT JOIN predicted_reference pred ON pred.julian_day_tt = er.julian_day_tt
                AND pred.test_type = REPLACE(d.slug, '_eclipse', '')
            WHERE er.id = ? AND er.run_id = ?
            """,
            (result_id, run_id),
        )
        row = await cursor.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Result not found")
    return dict(row)
