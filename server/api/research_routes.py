"""Research job endpoints."""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from server.auth import require_user
from server.db import get_async_db
from server.research.instructions import render_instructions

router = APIRouter(prefix="/api/research")

_ALLOWED_VIEWS = {"v_solar_position", "v_moon_position", "v_combined_position"}
_ALLOWED_STATUSES = {"active", "paused", "completed"}


class CreateJobBody(BaseModel):
    name: str
    param_set_id: int
    dataset_id: int
    view_name: str
    allowlist: list[str]
    date_start: str | None = None
    date_end: str | None = None


class UpdateJobBody(BaseModel):
    status: str | None = None


@router.get("")
async def list_research_jobs():
    async with get_async_db() as conn:
        rows = await conn.fetch(
            "SELECT * FROM research_jobs ORDER BY created_at DESC"
        )
    return [dict(r) for r in rows]


@router.post("", status_code=201)
async def create_research_job(body: CreateJobBody, request: Request):
    await require_user(request)
    if body.view_name not in _ALLOWED_VIEWS:
        raise HTTPException(status_code=422, detail=f"Unknown view_name: {body.view_name}")
    if not body.allowlist:
        raise HTTPException(status_code=422, detail="allowlist must be non-empty")

    async with get_async_db() as conn:
        ps = await conn.fetchrow("SELECT id, name FROM param_sets WHERE id=$1", body.param_set_id)
        if not ps:
            raise HTTPException(status_code=404, detail="param_set_id not found")
        ds = await conn.fetchrow("SELECT id, slug FROM datasets WHERE id=$1", body.dataset_id)
        if not ds:
            raise HTTPException(status_code=404, detail="dataset_id not found")

        job_id = await conn.fetchval(
            "INSERT INTO research_jobs (name, param_set_id, dataset_id, view_name, allowlist, date_start, date_end) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING id",
            body.name, body.param_set_id, body.dataset_id, body.view_name,
            body.allowlist, body.date_start, body.date_end,
        )

        instructions = render_instructions(
            job_id=job_id,
            job_name=body.name,
            dataset_slug=ds["slug"],
            view_name=body.view_name,
            allowlist=body.allowlist,
            param_set_id=body.param_set_id,
            date_start=body.date_start,
            date_end=body.date_end,
        )
        await conn.execute(
            "UPDATE research_jobs SET instructions=$1 WHERE id=$2",
            instructions, job_id,
        )

        row = await conn.fetchrow("SELECT * FROM research_jobs WHERE id=$1", job_id)
    return dict(row)


@router.get("/{job_id}")
async def get_research_job(job_id: int):
    async with get_async_db() as conn:
        row = await conn.fetchrow("SELECT * FROM research_jobs WHERE id=$1", job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Research job not found")
    return dict(row)


@router.patch("/{job_id}")
async def update_research_job(job_id: int, body: UpdateJobBody, request: Request):
    await require_user(request)
    if body.status is not None and body.status not in _ALLOWED_STATUSES:
        raise HTTPException(status_code=422, detail=f"status must be one of {_ALLOWED_STATUSES}")

    async with get_async_db() as conn:
        existing = await conn.fetchrow("SELECT id FROM research_jobs WHERE id=$1", job_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Research job not found")
        if body.status is not None:
            await conn.execute(
                "UPDATE research_jobs SET status=$1, updated_at=to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS') WHERE id=$2",
                body.status, job_id,
            )
        row = await conn.fetchrow("SELECT * FROM research_jobs WHERE id=$1", job_id)
    return dict(row)
