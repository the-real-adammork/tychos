"""Eclipse results routes: paginated list per run."""
from fastapi import APIRouter, HTTPException, Query

from server.db import get_async_db

router = APIRouter(prefix="/api/results")

PAGE_SIZE = 50

# Accuracy thresholds (arcminutes)
PASS_THRESHOLD = 30.0
CLOSE_THRESHOLD = 60.0


def _accuracy_label(moon_error):
    if moon_error is None:
        return "unknown"
    if moon_error < PASS_THRESHOLD:
        return "pass"
    if moon_error < CLOSE_THRESHOLD:
        return "close"
    return "fail"


def _enrich(row_dict):
    """Add accuracy label from stored moon_error_arcmin."""
    d = dict(row_dict)
    d["accuracy"] = _accuracy_label(d.get("moon_error_arcmin"))
    return d


@router.get("/{run_id}")
async def list_results(
    run_id: int,
    page: int = Query(default=1, ge=1),
    catalog_type: str | None = Query(default=None),
    accuracy: str | None = Query(default=None),
):
    """Paginated eclipse results for a run."""
    async with get_async_db() as conn:
        run_cursor = await conn.execute(
            "SELECT id, test_type FROM runs WHERE id = ?", (run_id,)
        )
        run_row = await run_cursor.fetchone()
        if run_row is None:
            raise HTTPException(status_code=404, detail="Run not found")

        conditions = ["er.run_id = ?"]
        values: list = [run_id]

        if catalog_type is not None:
            conditions.append("er.catalog_type = ?")
            values.append(catalog_type)

        # Accuracy filter via moon_error_arcmin
        if accuracy == "pass":
            conditions.append("er.moon_error_arcmin IS NOT NULL AND er.moon_error_arcmin < ?")
            values.append(PASS_THRESHOLD)
        elif accuracy == "close":
            conditions.append("er.moon_error_arcmin IS NOT NULL AND er.moon_error_arcmin >= ? AND er.moon_error_arcmin < ?")
            values.extend([PASS_THRESHOLD, CLOSE_THRESHOLD])
        elif accuracy == "fail":
            conditions.append("(er.moon_error_arcmin IS NULL OR er.moon_error_arcmin >= ?)")
            values.append(CLOSE_THRESHOLD)
        elif accuracy == "close+fail":
            conditions.append("(er.moon_error_arcmin IS NULL OR er.moon_error_arcmin >= ?)")
            values.append(PASS_THRESHOLD)

        where_clause = "WHERE " + " AND ".join(conditions)

        # Total count with filters
        total_cursor = await conn.execute(
            f"SELECT COUNT(*) FROM eclipse_results er {where_clause}", values
        )
        total = (await total_cursor.fetchone())[0]

        # Stats (always for the full run, ignoring accuracy filter)
        stats_cursor = await conn.execute(
            """
            SELECT
                SUM(CASE WHEN moon_error_arcmin IS NOT NULL AND moon_error_arcmin < ? THEN 1 ELSE 0 END) AS pass_count,
                SUM(CASE WHEN moon_error_arcmin IS NOT NULL AND moon_error_arcmin >= ? AND moon_error_arcmin < ? THEN 1 ELSE 0 END) AS close_count,
                SUM(CASE WHEN moon_error_arcmin IS NULL OR moon_error_arcmin >= ? THEN 1 ELSE 0 END) AS fail_count
            FROM eclipse_results
            WHERE run_id = ?
            """,
            (PASS_THRESHOLD, PASS_THRESHOLD, CLOSE_THRESHOLD, CLOSE_THRESHOLD, run_id),
        )
        stats_row = await stats_cursor.fetchone()

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
        "results": [_enrich(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": PAGE_SIZE,
        "stats": {
            "pass": stats_row["pass_count"] or 0,
            "close": stats_row["close_count"] or 0,
            "fail": stats_row["fail_count"] or 0,
        },
    }


@router.get("/{run_id}/{result_id}")
async def get_result(run_id: int, result_id: int):
    """Get a single eclipse result with run context and JPL comparison."""
    async with get_async_db() as conn:
        cursor = await conn.execute(
            """
            SELECT er.*, r.test_type, pv.version_number,
                   ps.id AS param_set_id, ps.name AS param_set_name,
                   jpl.sun_ra_rad AS jpl_sun_ra_rad, jpl.sun_dec_rad AS jpl_sun_dec_rad,
                   jpl.moon_ra_rad AS jpl_moon_ra_rad, jpl.moon_dec_rad AS jpl_moon_dec_rad,
                   jpl.separation_arcmin AS jpl_separation_arcmin
            FROM eclipse_results er
            JOIN runs r ON er.run_id = r.id
            JOIN param_versions pv ON r.param_version_id = pv.id
            JOIN param_sets ps ON pv.param_set_id = ps.id
            LEFT JOIN jpl_reference jpl ON jpl.julian_day_tt = er.julian_day_tt
                AND jpl.test_type = r.test_type
            WHERE er.id = ? AND er.run_id = ?
            """,
            (result_id, run_id),
        )
        row = await cursor.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Result not found")
    return _enrich(row)
