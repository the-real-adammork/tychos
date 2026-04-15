"""Run routes: list, create, get."""
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from server.auth import require_user
from server.db import get_async_db

router = APIRouter(prefix="/api/runs")


def _row_to_dict(row) -> dict:
    return dict(row)


@router.get("")
async def list_runs(
    param_set_id: int | None = Query(default=None),
    status: str | None = Query(default=None),
):
    """List runs with param set and dataset info."""
    conditions = []
    values: list = []

    if param_set_id is not None:
        values.append(param_set_id)
        conditions.append(f"pv.param_set_id = ${len(values)}")
    if status is not None:
        values.append(status)
        conditions.append(f"r.status = ${len(values)}")

    where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    async with get_async_db() as conn:
        rows = await conn.fetch(
            f"""
            SELECT r.*, pv.version_number, ps.id AS param_set_id, ps.name AS param_set_name,
                   u.name AS owner_name, d.slug AS dataset_slug, d.name AS dataset_name
            FROM runs r
            JOIN param_versions pv ON r.param_version_id = pv.id
            JOIN param_sets ps ON pv.param_set_id = ps.id
            JOIN users u ON ps.owner_id = u.id
            JOIN datasets d ON r.dataset_id = d.id
            {where_clause}
            ORDER BY r.created_at DESC
            LIMIT 100
            """,
            *values,
        )

        result = []
        for row in rows:
            d = _row_to_dict(row)
            if d["status"] == "done":
                mean_err = await conn.fetchval(
                    "SELECT AVG(tychos_error_arcmin) FROM eclipse_results WHERE run_id = $1",
                    d["id"],
                )
                d["mean_tychos_error"] = round(mean_err, 2) if mean_err else None
            else:
                d["mean_tychos_error"] = None
            result.append(d)

    return result


class CreateRunBody(BaseModel):
    param_set_id: int
    dataset_id: int


@router.post("", status_code=201)
async def create_run(body: CreateRunBody, request: Request):
    """Queue a new run for the latest version of a param set + dataset. Auth required."""
    user = await require_user(request)

    async with get_async_db() as conn:
        ds_row = await conn.fetchrow(
            "SELECT id FROM datasets WHERE id = $1", body.dataset_id
        )
        if ds_row is None:
            raise HTTPException(status_code=404, detail="Dataset not found")

        latest_ver = await conn.fetchrow(
            """
            SELECT id FROM param_versions
            WHERE param_set_id = $1
            ORDER BY version_number DESC
            LIMIT 1
            """,
            body.param_set_id,
        )
        if latest_ver is None:
            raise HTTPException(status_code=404, detail="Param set not found or has no versions")

        param_version_id = latest_ver["id"]

        new_run_id = await conn.fetchval(
            """
            INSERT INTO runs (param_version_id, dataset_id, status)
            VALUES ($1, $2, 'queued') RETURNING id
            """,
            param_version_id, body.dataset_id,
        )

        row = await conn.fetchrow(
            """
            SELECT r.*, pv.version_number, ps.id AS param_set_id, ps.name AS param_set_name,
                   u.name AS owner_name, d.slug AS dataset_slug, d.name AS dataset_name
            FROM runs r
            JOIN param_versions pv ON r.param_version_id = pv.id
            JOIN param_sets ps ON pv.param_set_id = ps.id
            JOIN users u ON ps.owner_id = u.id
            JOIN datasets d ON r.dataset_id = d.id
            WHERE r.id = $1
            """,
            new_run_id,
        )

    return _row_to_dict(row)


@router.post("/{run_id}/rerun", status_code=202)
async def rerun_run(run_id: int, request: Request):
    """Force re-run: delete old eclipse_results and re-queue the run.

    Keeps the same run row (same param_version + dataset) so that history
    references remain stable. Worker will pick it up on the next poll.
    """
    await require_user(request)

    async with get_async_db() as conn:
        row = await conn.fetchrow("SELECT id FROM runs WHERE id = $1", run_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Run not found")

        await conn.execute("DELETE FROM eclipse_results WHERE run_id = $1", run_id)
        await conn.execute(
            """
            UPDATE runs
               SET status = 'queued',
                   total_eclipses = NULL,
                   detected = NULL,
                   started_at = NULL,
                   completed_at = NULL,
                   mean_sun_diff = NULL,
                   mean_moon_diff = NULL,
                   mean_timing_offset = NULL
             WHERE id = $1
            """,
            run_id,
        )

    return {"id": run_id, "status": "queued"}


@router.get("/{run_id}")
async def get_run(run_id: int):
    """Get a single run with param set and dataset info."""
    async with get_async_db() as conn:
        row = await conn.fetchrow(
            """
            SELECT r.*, pv.version_number, ps.id AS param_set_id, ps.name AS param_set_name,
                   u.name AS owner_name, d.slug AS dataset_slug, d.name AS dataset_name
            FROM runs r
            JOIN param_versions pv ON r.param_version_id = pv.id
            JOIN param_sets ps ON pv.param_set_id = ps.id
            JOIN users u ON ps.owner_id = u.id
            JOIN datasets d ON r.dataset_id = d.id
            WHERE r.id = $1
            """,
            run_id,
        )

    if row is None:
        raise HTTPException(status_code=404, detail="Run not found")

    return _row_to_dict(row)
