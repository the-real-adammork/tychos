"""Run routes: list, create, get."""
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from server.auth import require_user
from server.db import get_async_db

router = APIRouter(prefix="/api/runs")

VALID_TEST_TYPES = {"solar", "lunar"}


def _row_to_dict(row) -> dict:
    return dict(row)


@router.get("")
async def list_runs(
    param_set_id: int | None = Query(default=None),
    status: str | None = Query(default=None),
):
    """List runs with param set info. Filterable by param_set_id and status. Limit 100."""
    conditions = []
    values: list = []

    if param_set_id is not None:
        conditions.append("pv.param_set_id = ?")
        values.append(param_set_id)
    if status is not None:
        conditions.append("r.status = ?")
        values.append(status)

    where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    async with get_async_db() as conn:
        cursor = await conn.execute(
            f"""
            SELECT r.*, pv.version_number, ps.id AS param_set_id, ps.name AS param_set_name, u.name AS owner_name
            FROM runs r
            JOIN param_versions pv ON r.param_version_id = pv.id
            JOIN param_sets ps ON pv.param_set_id = ps.id
            JOIN users u ON ps.owner_id = u.id
            {where_clause}
            ORDER BY r.created_at DESC
            LIMIT 100
            """,
            values,
        )
        rows = await cursor.fetchall()

    return [_row_to_dict(r) for r in rows]


class CreateRunBody(BaseModel):
    param_set_id: int
    test_type: str


@router.post("", status_code=201)
async def create_run(body: CreateRunBody, request: Request):
    """Force-queue a new run for the latest version of a param set. Auth required."""
    user = await require_user(request)

    if body.test_type not in VALID_TEST_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"test_type must be one of: {', '.join(sorted(VALID_TEST_TYPES))}",
        )

    async with get_async_db() as conn:
        # Find latest version for this param set
        ver_cursor = await conn.execute(
            """
            SELECT id FROM param_versions
            WHERE param_set_id = ?
            ORDER BY version_number DESC
            LIMIT 1
            """,
            (body.param_set_id,),
        )
        latest_ver = await ver_cursor.fetchone()
        if latest_ver is None:
            raise HTTPException(status_code=404, detail="Param set not found or has no versions")

        param_version_id = latest_ver["id"]

        cursor = await conn.execute(
            """
            INSERT INTO runs (param_version_id, test_type, status)
            VALUES (?, ?, 'queued')
            """,
            (param_version_id, body.test_type),
        )
        await conn.commit()

        row_cursor = await conn.execute(
            """
            SELECT r.*, pv.version_number, ps.id AS param_set_id, ps.name AS param_set_name, u.name AS owner_name
            FROM runs r
            JOIN param_versions pv ON r.param_version_id = pv.id
            JOIN param_sets ps ON pv.param_set_id = ps.id
            JOIN users u ON ps.owner_id = u.id
            WHERE r.id = ?
            """,
            (cursor.lastrowid,),
        )
        row = await row_cursor.fetchone()

    return _row_to_dict(row)


@router.get("/{run_id}")
async def get_run(run_id: int):
    """Get a single run with param set info."""
    async with get_async_db() as conn:
        cursor = await conn.execute(
            """
            SELECT r.*, pv.version_number, ps.id AS param_set_id, ps.name AS param_set_name, u.name AS owner_name
            FROM runs r
            JOIN param_versions pv ON r.param_version_id = pv.id
            JOIN param_sets ps ON pv.param_set_id = ps.id
            JOIN users u ON ps.owner_id = u.id
            WHERE r.id = ?
            """,
            (run_id,),
        )
        row = await cursor.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Run not found")

    return _row_to_dict(row)
