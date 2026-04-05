"""Eclipse results routes: paginated list per run."""
from fastapi import APIRouter, HTTPException, Query

from server.db import get_async_db

router = APIRouter(prefix="/api/results")

PAGE_SIZE = 50

# JPL accuracy thresholds (arcminutes) — only used when threshold detection fails
JPL_CLOSE_THRESHOLD = 60.0


def _compute_status(detected, moon_error_arcmin):
    """Compute overall status.

    - threshold pass → "pass"
    - threshold fail + JPL close enough (<60') → "pass" (jpl_rescued)
    - threshold fail + JPL fail (>=60' or unknown) → "fail"
    """
    if detected:
        return "pass"
    if moon_error_arcmin is not None and moon_error_arcmin < JPL_CLOSE_THRESHOLD:
        return "pass"
    return "fail"


def _enrich(row_dict):
    """Add computed status and jpl_rescued flag."""
    d = dict(row_dict)
    detected = d.get("detected") in (1, True)
    moon_error = d.get("moon_error_arcmin")
    d["status"] = _compute_status(detected, moon_error)
    d["threshold_pass"] = detected
    d["jpl_rescued"] = not detected and moon_error is not None and moon_error < JPL_CLOSE_THRESHOLD
    return d


@router.get("/{run_id}")
async def list_results(
    run_id: int,
    page: int = Query(default=1, ge=1),
    catalog_type: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
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

        # Status filter:
        # pass = threshold detected OR (not detected but moon_error < 60)
        # fail = not detected AND (moon_error >= 60 or null)
        if status_filter == "pass":
            conditions.append(
                "(er.detected = 1 OR (er.moon_error_arcmin IS NOT NULL AND er.moon_error_arcmin < ?))"
            )
            values.append(JPL_CLOSE_THRESHOLD)
        elif status_filter == "fail":
            conditions.append(
                "er.detected = 0 AND (er.moon_error_arcmin IS NULL OR er.moon_error_arcmin >= ?)"
            )
            values.append(JPL_CLOSE_THRESHOLD)
        elif status_filter == "threshold_pass":
            conditions.append("er.detected = 1")
        elif status_filter == "threshold_fail":
            conditions.append("er.detected = 0")

        where_clause = "WHERE " + " AND ".join(conditions)

        # Total count with filters
        total_cursor = await conn.execute(
            f"SELECT COUNT(*) FROM eclipse_results er {where_clause}", values
        )
        total = (await total_cursor.fetchone())[0]

        # Stats (always for full run)
        stats_cursor = await conn.execute(
            """
            SELECT
                SUM(CASE WHEN detected = 1 THEN 1 ELSE 0 END) AS threshold_pass,
                SUM(CASE WHEN detected = 0 THEN 1 ELSE 0 END) AS threshold_fail,
                SUM(CASE WHEN detected = 0 AND moon_error_arcmin IS NOT NULL AND moon_error_arcmin < ? THEN 1 ELSE 0 END) AS jpl_rescued,
                SUM(CASE WHEN detected = 1 OR (moon_error_arcmin IS NOT NULL AND moon_error_arcmin < ?) THEN 1 ELSE 0 END) AS overall_pass,
                SUM(CASE WHEN detected = 0 AND (moon_error_arcmin IS NULL OR moon_error_arcmin >= ?) THEN 1 ELSE 0 END) AS overall_fail,
                COUNT(*) AS total
            FROM eclipse_results
            WHERE run_id = ?
            """,
            (JPL_CLOSE_THRESHOLD, JPL_CLOSE_THRESHOLD, JPL_CLOSE_THRESHOLD, run_id),
        )
        s = await stats_cursor.fetchone()

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
            "threshold_pass": s["threshold_pass"] or 0,
            "threshold_fail": s["threshold_fail"] or 0,
            "jpl_rescued": s["jpl_rescued"] or 0,
            "overall_pass": s["overall_pass"] or 0,
            "overall_fail": s["overall_fail"] or 0,
            "total": s["total"] or 0,
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
