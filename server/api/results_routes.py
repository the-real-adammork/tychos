"""Eclipse results routes: paginated list per run."""
from fastapi import APIRouter, HTTPException, Query

from server.db import get_async_db

router = APIRouter(prefix="/api/results")

PAGE_SIZE = 50


def _row_to_dict(row) -> dict:
    return dict(row)


@router.get("/{run_id}")
async def list_results(
    run_id: int,
    page: int = Query(default=1, ge=1),
    catalog_type: str | None = Query(default=None),
    detected: str | None = Query(default=None),
):
    """Paginated eclipse results for a run.

    Query params:
    - page: 1-based page number (default 1)
    - catalog_type: filter by catalog_type
    - detected: "true" or "false"
    """
    async with get_async_db() as conn:
        # Verify run exists
        run_cursor = await conn.execute("SELECT id FROM runs WHERE id = ?", (run_id,))
        run_row = await run_cursor.fetchone()
        if run_row is None:
            raise HTTPException(status_code=404, detail="Run not found")

        conditions = ["run_id = ?"]
        values: list = [run_id]

        if catalog_type is not None:
            conditions.append("catalog_type = ?")
            values.append(catalog_type)

        if detected is not None:
            if detected.lower() == "true":
                conditions.append("detected = 1")
            elif detected.lower() == "false":
                conditions.append("detected = 0")
            else:
                raise HTTPException(
                    status_code=422, detail="detected must be 'true' or 'false'"
                )

        where_clause = "WHERE " + " AND ".join(conditions)

        total_cursor = await conn.execute(
            f"SELECT COUNT(*) FROM eclipse_results {where_clause}", values
        )
        total_row = await total_cursor.fetchone()
        total = total_row[0]

        offset = (page - 1) * PAGE_SIZE
        rows_cursor = await conn.execute(
            f"""
            SELECT * FROM eclipse_results
            {where_clause}
            ORDER BY julian_day_tt ASC
            LIMIT ? OFFSET ?
            """,
            values + [PAGE_SIZE, offset],
        )
        rows = await rows_cursor.fetchall()

    return {
        "results": [_row_to_dict(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": PAGE_SIZE,
    }


@router.get("/{run_id}/{result_id}")
async def get_result(run_id: int, result_id: int):
    """Get a single eclipse result with run context."""
    async with get_async_db() as conn:
        cursor = await conn.execute(
            """
            SELECT er.*, r.test_type, pv.version_number,
                   ps.id AS param_set_id, ps.name AS param_set_name
            FROM eclipse_results er
            JOIN runs r ON er.run_id = r.id
            JOIN param_versions pv ON r.param_version_id = pv.id
            JOIN param_sets ps ON pv.param_set_id = ps.id
            WHERE er.id = ? AND er.run_id = ?
            """,
            (result_id, run_id),
        )
        row = await cursor.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Result not found")
    return _row_to_dict(row)
