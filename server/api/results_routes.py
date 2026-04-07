"""Eclipse results routes: paginated list per run with error metrics."""
from fastapi import APIRouter, HTTPException, Query

from server.db import get_async_db

router = APIRouter(prefix="/api/results")

PAGE_SIZE = 50


# Allowed sort columns mapped to safe SQL column names
_SORTABLE_COLUMNS = {
    "date": "er.julian_day_tt",
    "catalog_type": "er.catalog_type",
    "magnitude": "er.magnitude",
    "min_separation_arcmin": "er.min_separation_arcmin",
    "tychos_error_arcmin": "er.tychos_error_arcmin",
    "jpl_error_arcmin": "er.jpl_error_arcmin",
    "timing_offset_min": "er.timing_offset_min",
    "jpl_timing_offset_min": "er.jpl_timing_offset_min",
}


@router.get("/{run_id}")
async def list_results(
    run_id: int,
    page: int = Query(default=1, ge=1),
    catalog_type: str | None = Query(default=None),
    min_tychos_error: float | None = Query(default=None),
    max_tychos_error: float | None = Query(default=None),
    saros: int | None = Query(default=None),
    sort_by: str = Query(default="date"),
    sort_dir: str = Query(default="asc"),
):
    """Paginated eclipse results for a run with error metrics."""
    async with get_async_db() as conn:
        run_cursor = await conn.execute(
            "SELECT id, dataset_id FROM runs WHERE id = ?", (run_id,)
        )
        run_row = await run_cursor.fetchone()
        if run_row is None:
            raise HTTPException(status_code=404, detail="Run not found")
        dataset_id = run_row["dataset_id"]

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

        if saros is not None:
            conditions.append(
                "er.julian_day_tt IN (SELECT julian_day_tt FROM eclipse_catalog WHERE dataset_id = ? AND saros_num = ?)"
            )
            values.append(dataset_id)
            values.append(saros)

        where_clause = "WHERE " + " AND ".join(conditions)

        # Total count with filters
        total_cursor = await conn.execute(
            f"SELECT COUNT(*) FROM eclipse_results er {where_clause}", values
        )
        total = (await total_cursor.fetchone())[0]

        # Stats with the same filters applied as the row query
        stats_cursor = await conn.execute(
            f"""
            SELECT
                COUNT(*) AS total,
                AVG(tychos_error_arcmin) AS mean_tychos_error,
                AVG(jpl_error_arcmin) AS mean_jpl_error,
                MAX(tychos_error_arcmin) AS max_tychos_error,
                MAX(jpl_error_arcmin) AS max_jpl_error
            FROM eclipse_results er
            {where_clause}
            """,
            values,
        )
        s = await stats_cursor.fetchone()

        # Median (SQLite doesn't have MEDIAN, compute in Python) — also filtered
        median_cursor = await conn.execute(
            f"SELECT tychos_error_arcmin, jpl_error_arcmin FROM eclipse_results er {where_clause} ORDER BY tychos_error_arcmin",
            values,
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

        # Paginated results — validate sort args
        sort_col = _SORTABLE_COLUMNS.get(sort_by, "er.julian_day_tt")
        sort_dir_sql = "DESC" if sort_dir.lower() == "desc" else "ASC"
        offset = (page - 1) * PAGE_SIZE
        rows_cursor = await conn.execute(
            f"""
            SELECT er.*
            FROM eclipse_results er
            {where_clause}
            ORDER BY {sort_col} {sort_dir_sql} NULLS LAST, er.julian_day_tt ASC
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


@router.get("/{run_id}/saros")
async def list_saros_groups(
    run_id: int,
    catalog_type: str | None = Query(default=None),
    min_tychos_error: float | None = Query(default=None),
    max_tychos_error: float | None = Query(default=None),
):
    """Aggregate eclipse results by Saros series for a single run.

    Returns one row per Saros series with count, year span, and mean errors.
    Filters apply, but `saros` itself is not filtered (this endpoint IS the
    grouping). Series are sorted by mean Tychos error descending (worst first).
    """
    async with get_async_db() as conn:
        run_cursor = await conn.execute(
            "SELECT id, dataset_id FROM runs WHERE id = ?", (run_id,)
        )
        run_row = await run_cursor.fetchone()
        if run_row is None:
            raise HTTPException(status_code=404, detail="Run not found")
        dataset_id = run_row["dataset_id"]

        conditions = ["er.run_id = ?", "ec.dataset_id = ?", "ec.saros_num IS NOT NULL"]
        values: list = [run_id, dataset_id]

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

        cursor = await conn.execute(
            f"""
            SELECT
                ec.saros_num,
                COUNT(*) AS count,
                MIN(SUBSTR(er.date, 1, 4)) AS year_start,
                MAX(SUBSTR(er.date, 1, 4)) AS year_end,
                AVG(er.tychos_error_arcmin) AS mean_tychos_error,
                AVG(er.jpl_error_arcmin) AS mean_jpl_error,
                MAX(er.tychos_error_arcmin) AS max_tychos_error,
                MAX(er.jpl_error_arcmin) AS max_jpl_error
            FROM eclipse_results er
            JOIN eclipse_catalog ec ON ec.julian_day_tt = er.julian_day_tt AND ec.dataset_id = ?
            {where_clause}
            GROUP BY ec.saros_num
            ORDER BY mean_tychos_error DESC
            """,
            [dataset_id] + values,
        )
        rows = await cursor.fetchall()

        groups = []
        for r in rows:
            d = dict(r)
            for k in ("mean_tychos_error", "mean_jpl_error", "max_tychos_error", "max_jpl_error"):
                if d[k] is not None:
                    d[k] = round(d[k], 2)
            groups.append(d)

    return {"groups": groups}


@router.get("/{run_id}/{result_id}")
async def get_result(run_id: int, result_id: int):
    """Get a single eclipse result with run context, JPL and predicted reference data."""
    async with get_async_db() as conn:
        cursor = await conn.execute(
            """
            SELECT er.*, r.dataset_id, d.slug AS dataset_slug, d.name AS dataset_name,
                   REPLACE(d.slug, '_eclipse', '') AS test_type, pv.version_number,
                   ps.id AS param_set_id, ps.name AS param_set_name,
                   ec.saros_num,
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
            LEFT JOIN eclipse_catalog ec ON ec.julian_day_tt = er.julian_day_tt
                AND ec.dataset_id = r.dataset_id
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

        result = dict(row)

        # Saros context: position in series + neighbors
        saros_num = result.get("saros_num")
        if saros_num is not None:
            dataset_id = result["dataset_id"]
            series_cursor = await conn.execute(
                """
                SELECT er.id, er.julian_day_tt, er.date, er.catalog_type,
                       er.tychos_error_arcmin, er.jpl_error_arcmin
                FROM eclipse_results er
                JOIN eclipse_catalog ec ON ec.julian_day_tt = er.julian_day_tt AND ec.dataset_id = ?
                WHERE er.run_id = ? AND ec.saros_num = ?
                ORDER BY er.julian_day_tt
                """,
                (dataset_id, run_id, saros_num),
            )
            series = [dict(r) for r in await series_cursor.fetchall()]
            position = next((i for i, s in enumerate(series) if s["id"] == result_id), 0)

            result["saros_total"] = len(series)
            result["saros_position"] = position + 1
            result["saros_year_start"] = series[0]["date"][:4] if series else None
            result["saros_year_end"] = series[-1]["date"][:4] if series else None

            # ±5 neighbors
            start = max(0, position - 5)
            end = min(len(series), position + 6)
            neighbors = []
            for i in range(start, end):
                s = series[i]
                neighbors.append({
                    "id": s["id"],
                    "date": s["date"],
                    "catalog_type": s["catalog_type"],
                    "position": i + 1,
                    "tychos_error_arcmin": round(s["tychos_error_arcmin"], 2) if s["tychos_error_arcmin"] is not None else None,
                    "jpl_error_arcmin": round(s["jpl_error_arcmin"], 2) if s["jpl_error_arcmin"] is not None else None,
                    "is_self": s["id"] == result_id,
                })
            result["saros_neighbors"] = neighbors
        else:
            result["saros_total"] = None
            result["saros_position"] = None
            result["saros_year_start"] = None
            result["saros_year_end"] = None
            result["saros_neighbors"] = []

    return result
