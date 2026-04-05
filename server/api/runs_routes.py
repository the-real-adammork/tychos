"""Run routes: list, create, get."""
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from server.auth import require_user
from server.db import get_db

router = APIRouter(prefix="/api/runs")

VALID_TEST_TYPES = {"solar", "lunar"}


def _row_to_dict(row) -> dict:
    return dict(row)


@router.get("")
def list_runs(
    param_set_id: int | None = Query(default=None),
    status: str | None = Query(default=None),
):
    """List runs with param set info. Filterable by param_set_id and status. Limit 100."""
    conditions = []
    values: list = []

    if param_set_id is not None:
        conditions.append("r.param_set_id = ?")
        values.append(param_set_id)
    if status is not None:
        conditions.append("r.status = ?")
        values.append(status)

    where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    with get_db() as conn:
        rows = conn.execute(
            f"""
            SELECT r.*, p.name AS param_set_name, u.name AS owner_name
            FROM runs r
            JOIN param_sets p ON r.param_set_id = p.id
            JOIN users u ON p.owner_id = u.id
            {where_clause}
            ORDER BY r.created_at DESC
            LIMIT 100
            """,
            values,
        ).fetchall()

    return [_row_to_dict(r) for r in rows]


class CreateRunBody(BaseModel):
    param_set_id: int
    test_type: str


@router.post("", status_code=201)
def create_run(body: CreateRunBody, request: Request):
    """Queue a new run. Auth required."""
    user = require_user(request)

    if body.test_type not in VALID_TEST_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"test_type must be one of: {', '.join(sorted(VALID_TEST_TYPES))}",
        )

    with get_db() as conn:
        param_set = conn.execute(
            "SELECT id FROM param_sets WHERE id = ?", (body.param_set_id,)
        ).fetchone()
        if param_set is None:
            raise HTTPException(status_code=404, detail="Param set not found")

        cursor = conn.execute(
            """
            INSERT INTO runs (param_set_id, test_type, status)
            VALUES (?, ?, 'queued')
            """,
            (body.param_set_id, body.test_type),
        )
        conn.commit()

        row = conn.execute(
            """
            SELECT r.*, p.name AS param_set_name, u.name AS owner_name
            FROM runs r
            JOIN param_sets p ON r.param_set_id = p.id
            JOIN users u ON p.owner_id = u.id
            WHERE r.id = ?
            """,
            (cursor.lastrowid,),
        ).fetchone()

    return _row_to_dict(row)


@router.get("/{run_id}")
def get_run(run_id: int):
    """Get a single run with param set info."""
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT r.*, p.name AS param_set_name, u.name AS owner_name
            FROM runs r
            JOIN param_sets p ON r.param_set_id = p.id
            JOIN users u ON p.owner_id = u.id
            WHERE r.id = ?
            """,
            (run_id,),
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Run not found")

    return _row_to_dict(row)
