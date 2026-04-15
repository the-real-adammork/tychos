"""GET /api/results/{run_id}/view/{view_name} — per-objective result lens."""
from fastapi import APIRouter, HTTPException
from server.db import get_async_db

router = APIRouter(prefix="/api/results")

_ALLOWED_VIEWS = {"v_solar_position", "v_moon_position", "v_combined_position"}


@router.get("/{run_id}/view/{view_name}")
async def get_view(run_id: int, view_name: str):
    if view_name not in _ALLOWED_VIEWS:
        raise HTTPException(status_code=404, detail=f"Unknown view: {view_name}")

    async with get_async_db() as conn:
        # Optional date filter: look up the run's date range (if any).
        job_range = await conn.fetchrow(
            "SELECT date_start, date_end FROM runs WHERE id = $1",
            run_id,
        )
        date_start = job_range["date_start"] if job_range else None
        date_end = job_range["date_end"] if job_range else None

        filters = ["run_id = $1"]
        args = [run_id]
        if date_start:
            filters.append(f"date >= ${len(args)+1}")
            args.append(date_start)
        if date_end:
            filters.append(f"date <= ${len(args)+1}")
            args.append(date_end)
        where = " AND ".join(filters)

        obj_row = await conn.fetchrow(
            f"SELECT AVG(error) AS objective, COUNT(*) AS n FROM {view_name} WHERE {where}",
            *args,
        )
        detail_rows = await conn.fetch(
            f"SELECT * FROM {view_name} WHERE {where} ORDER BY error DESC",
            *args,
        )

    return {
        "objective": float(obj_row["objective"]) if obj_row["objective"] is not None else None,
        "n_scored": int(obj_row["n"]),
        "detail": [dict(r) for r in detail_rows],
    }
