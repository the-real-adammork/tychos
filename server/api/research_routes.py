"""Research job endpoints."""
import asyncio
import hashlib
import json as _json
import os

import asyncpg as _asyncpg
from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel

from server.auth import require_user
from server.db import get_async_db
from server.research.allowlist import check_diff_against_allowlist, AllowlistViolation
from server.research.instructions import render_instructions

router = APIRouter(prefix="/api/research")

_ALLOWED_VIEWS = {"v_solar_position", "v_moon_position", "v_combined_position"}
_ALLOWED_STATUSES = {"active", "paused", "completed", "pending"}


class CreateJobBody(BaseModel):
    name: str
    param_set_id: int
    dataset_id: int
    view_name: str
    allowlist: list[str]
    date_start: str | None = None
    date_end: str | None = None
    model: str = "claude-sonnet-4-6"
    max_iterations: int = 40
    max_wall_clock_seconds: int = 3600
    no_improvement_plateau: int = 6


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
            "INSERT INTO research_jobs (name, param_set_id, dataset_id, view_name, allowlist, date_start, date_end, "
            "model, max_iterations, max_wall_clock_seconds, no_improvement_plateau, status) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,'pending') RETURNING id",
            body.name, body.param_set_id, body.dataset_id, body.view_name,
            body.allowlist, body.date_start, body.date_end,
            body.model, body.max_iterations, body.max_wall_clock_seconds, body.no_improvement_plateau,
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


class CreateVersionBody(BaseModel):
    params_json: str
    notes: str | None = None


@router.post("/{job_id}/version", status_code=201)
async def create_research_version(job_id: int, body: CreateVersionBody, request: Request):
    await require_user(request)
    async with get_async_db() as conn:
        job = await conn.fetchrow("SELECT * FROM research_jobs WHERE id=$1", job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Research job not found")

        # Baseline for diff: latest checkpoint on this param_set, else v1.
        base_row = await conn.fetchrow(
            "SELECT params_json FROM param_versions "
            "WHERE param_set_id=$1 AND is_checkpoint=TRUE "
            "ORDER BY version_number DESC LIMIT 1",
            job["param_set_id"],
        )
        if base_row is None:
            base_row = await conn.fetchrow(
                "SELECT params_json FROM param_versions WHERE param_set_id=$1 ORDER BY version_number ASC LIMIT 1",
                job["param_set_id"],
            )
        baseline = _json.loads(base_row["params_json"])

        try:
            new_params = _json.loads(body.params_json)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"params_json invalid: {exc}")

        try:
            check_diff_against_allowlist(
                new_params, baseline,
                allowlist_globs=list(job["allowlist"]),
                known_bodies=list(baseline.keys()),
            )
        except AllowlistViolation as exc:
            raise HTTPException(status_code=400, detail=f"allowlist violation: {exc}")

        # New version
        latest_num = await conn.fetchval(
            "SELECT COALESCE(MAX(version_number),0) FROM param_versions WHERE param_set_id=$1",
            job["param_set_id"],
        )
        md5 = hashlib.md5(_json.dumps(new_params, sort_keys=True).encode()).hexdigest()
        version_id = await conn.fetchval(
            "INSERT INTO param_versions (param_set_id, version_number, params_md5, params_json, notes) "
            "VALUES ($1,$2,$3,$4,$5) RETURNING id",
            job["param_set_id"], latest_num + 1, md5, body.params_json, body.notes,
        )
        run_id = await conn.fetchval(
            "INSERT INTO runs (param_version_id, dataset_id, status, date_start, date_end) "
            "VALUES ($1,$2,'queued',$3,$4) RETURNING id",
            version_id, job["dataset_id"], job["date_start"], job["date_end"],
        )

    return {"version_id": version_id, "run_id": run_id}


class LogIterationBody(BaseModel):
    param_version_id: int
    run_id: int | None = None
    kind: str
    objective: float | None = None
    aux_stats: dict | None = None


@router.get("/{job_id}/iterations")
async def list_iterations(job_id: int):
    async with get_async_db() as conn:
        rows = await conn.fetch(
            "SELECT * FROM research_iterations WHERE research_job_id=$1 ORDER BY created_at ASC",
            job_id,
        )
    return [dict(r) for r in rows]


@router.post("/{job_id}/iterations", status_code=201)
async def log_iteration(job_id: int, body: LogIterationBody, request: Request):
    await require_user(request)
    if body.kind not in ("iterate", "search_eval", "search_winner"):
        raise HTTPException(status_code=422, detail="Invalid kind")
    async with get_async_db() as conn:
        row = await conn.fetchrow(
            "INSERT INTO research_iterations (research_job_id, param_version_id, run_id, kind, objective, aux_stats) "
            "VALUES ($1,$2,$3,$4,$5,$6) RETURNING *",
            job_id, body.param_version_id, body.run_id, body.kind, body.objective,
            _json.dumps(body.aux_stats) if body.aux_stats else None,
        )
    return dict(row)


@router.post("/{job_id}/checkpoint/{version_id}")
async def mark_checkpoint(job_id: int, version_id: int, request: Request):
    await require_user(request)
    async with get_async_db() as conn:
        job = await conn.fetchrow("SELECT param_set_id FROM research_jobs WHERE id=$1", job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Research job not found")
        v = await conn.fetchrow(
            "SELECT id FROM param_versions WHERE id=$1 AND param_set_id=$2",
            version_id, job["param_set_id"],
        )
        if not v:
            raise HTTPException(status_code=404, detail="Version not found on this job's param set")
        row = await conn.fetchrow(
            "UPDATE param_versions SET is_checkpoint=TRUE WHERE id=$1 RETURNING *",
            version_id,
        )
    return dict(row)


class SearchBody(BaseModel):
    param_keys: list[str]
    budget: int = 60
    scale: float = 0.01


@router.post("/{job_id}/search")
async def run_research_search(job_id: int, body: SearchBody, request: Request):
    await require_user(request)
    from server.research.search_engine import run_search
    from server.research.allowlist import expand_globs
    from server.services.scanner import scan_solar_eclipses, scan_lunar_eclipses
    import math

    async with get_async_db() as conn:
        job = await conn.fetchrow("SELECT * FROM research_jobs WHERE id=$1", job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Research job not found")
        # Starting params = latest checkpoint or v1
        row = await conn.fetchrow(
            "SELECT id, params_json FROM param_versions WHERE param_set_id=$1 AND is_checkpoint=TRUE ORDER BY version_number DESC LIMIT 1",
            job["param_set_id"],
        )
        if row is None:
            row = await conn.fetchrow(
                "SELECT id, params_json FROM param_versions WHERE param_set_id=$1 ORDER BY version_number ASC LIMIT 1",
                job["param_set_id"],
            )
        starting = _json.loads(row["params_json"])

        allowed = expand_globs(list(job["allowlist"]), list(starting.keys()))
        forbidden = [k for k in body.param_keys if k not in allowed]
        if forbidden:
            raise HTTPException(status_code=400, detail=f"param_keys not in allowlist: {forbidden}")

        ds = await conn.fetchrow("SELECT slug, scan_window_hours FROM datasets WHERE id=$1", job["dataset_id"])
        jpl_rows = await conn.fetch(
            "SELECT julian_day_tt, best_jd, sun_ra_rad, sun_dec_rad, moon_ra_rad, moon_dec_rad "
            "FROM jpl_reference WHERE dataset_id=$1",
            job["dataset_id"],
        )
        cat_filters = ["dataset_id=$1"]
        cat_args = [job["dataset_id"]]
        if job["date_start"]:
            cat_filters.append(f"date >= ${len(cat_args)+1}")
            cat_args.append(job["date_start"])
        if job["date_end"]:
            cat_filters.append(f"date <= ${len(cat_args)+1}")
            cat_args.append(job["date_end"])
        eclipses = [dict(r) for r in await conn.fetch(
            f"SELECT catalog_number, julian_day_tt, date, type, magnitude, gamma, "
            f"pen_mag, um_mag FROM eclipse_catalog WHERE {' AND '.join(cat_filters)} ORDER BY julian_day_tt",
            *cat_args,
        )]

    jpl_by_jd = {r["julian_day_tt"]: r for r in jpl_rows}
    jpl_best_lookup = {jd: r["best_jd"] for jd, r in jpl_by_jd.items() if r["best_jd"] is not None}

    RAD_TO_ARCMIN = (180.0 / math.pi) * 60.0

    def _evaluate(candidate: dict) -> float:
        scan_fn = scan_solar_eclipses if ds["slug"] == "solar_eclipse" else scan_lunar_eclipses
        results = scan_fn(
            candidate, eclipses,
            half_window_hours=float(ds["scan_window_hours"]),
            jpl_best_jd_by_catalog_jd=jpl_best_lookup,
        )
        errs = []
        for r in results:
            jpl = jpl_by_jd.get(r["julian_day_tt"])
            if not jpl or r.get("tychos_sun_ra_at_jpl_rad") is None:
                continue
            cos_s = math.cos(jpl["sun_dec_rad"])
            cos_m = math.cos(jpl["moon_dec_rad"])
            s_dra = (r["tychos_sun_ra_at_jpl_rad"] - jpl["sun_ra_rad"]) * cos_s * RAD_TO_ARCMIN
            s_ddec = (r["tychos_sun_dec_at_jpl_rad"] - jpl["sun_dec_rad"]) * RAD_TO_ARCMIN
            if job["view_name"] == "v_solar_position":
                errs.append(math.sqrt(s_dra*s_dra + s_ddec*s_ddec))
            else:
                m_dra = (r["tychos_moon_ra_at_jpl_rad"] - jpl["moon_ra_rad"]) * cos_m * RAD_TO_ARCMIN
                m_ddec = (r["tychos_moon_dec_at_jpl_rad"] - jpl["moon_dec_rad"]) * RAD_TO_ARCMIN
                if job["view_name"] == "v_moon_position":
                    errs.append(math.sqrt(m_dra*m_dra + m_ddec*m_ddec))
                else:
                    errs.append(math.sqrt(s_dra*s_dra + s_ddec*s_ddec + m_dra*m_dra + m_ddec*m_ddec))
        return float("inf") if not errs else sum(errs)/len(errs)

    search_result = run_search(
        current=starting,
        param_keys=body.param_keys,
        evaluate=_evaluate,
        budget=body.budget,
        scale=body.scale,
    )

    improved = search_result.best_objective < search_result.starting_objective
    winner_version_id = None
    winner_run_id = None

    if improved:
        async with get_async_db() as conn:
            job = await conn.fetchrow("SELECT * FROM research_jobs WHERE id=$1", job_id)
            latest_num = await conn.fetchval(
                "SELECT COALESCE(MAX(version_number),0) FROM param_versions WHERE param_set_id=$1",
                job["param_set_id"],
            )
            params_json = _json.dumps(search_result.best_params, sort_keys=True)
            md5 = hashlib.md5(params_json.encode()).hexdigest()
            winner_version_id = await conn.fetchval(
                "INSERT INTO param_versions (param_set_id, version_number, params_md5, params_json, notes, is_checkpoint) "
                "VALUES ($1,$2,$3,$4,$5,TRUE) RETURNING id",
                job["param_set_id"], latest_num + 1, md5, params_json,
                f"search winner: {body.param_keys} (budget {body.budget})",
            )
            winner_run_id = await conn.fetchval(
                "INSERT INTO runs (param_version_id, dataset_id, status, date_start, date_end) "
                "VALUES ($1,$2,'queued',$3,$4) RETURNING id",
                winner_version_id, job["dataset_id"], job["date_start"], job["date_end"],
            )
            await conn.execute(
                "INSERT INTO research_iterations (research_job_id, param_version_id, run_id, kind, objective) "
                "VALUES ($1,$2,$3,'search_winner',$4)",
                job_id, winner_version_id, winner_run_id, search_result.best_objective,
            )

    return {
        "starting_objective": search_result.starting_objective,
        "best_objective": search_result.best_objective,
        "delta": search_result.best_objective - search_result.starting_objective,
        "improved": improved,
        "n_evals": search_result.n_evals,
        "winner_version_id": winner_version_id,
        "winner_run_id": winner_run_id,
    }


@router.post("/{job_id}/restore/{version_id}", status_code=201)
async def restore_from_version(job_id: int, version_id: int, request: Request):
    await require_user(request)
    async with get_async_db() as conn:
        job = await conn.fetchrow("SELECT * FROM research_jobs WHERE id=$1", job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Research job not found")
        src = await conn.fetchrow(
            "SELECT params_json FROM param_versions WHERE id=$1 AND param_set_id=$2",
            version_id, job["param_set_id"],
        )
        if not src:
            raise HTTPException(status_code=404, detail="Source version not found on this job's param set")
        params_json = src["params_json"]
        md5 = hashlib.md5(_json.dumps(_json.loads(params_json), sort_keys=True).encode()).hexdigest()
        latest_num = await conn.fetchval(
            "SELECT COALESCE(MAX(version_number),0) FROM param_versions WHERE param_set_id=$1",
            job["param_set_id"],
        )
        new_version_id = await conn.fetchval(
            "INSERT INTO param_versions (param_set_id, version_number, parent_version_id, params_md5, params_json, notes) "
            "VALUES ($1,$2,$3,$4,$5,$6) RETURNING id",
            job["param_set_id"], latest_num + 1, version_id, md5, params_json,
            f"restored from version {version_id}",
        )
        run_id = await conn.fetchval(
            "INSERT INTO runs (param_version_id, dataset_id, status, date_start, date_end) "
            "VALUES ($1,$2,'queued',$3,$4) RETURNING id",
            new_version_id, job["dataset_id"], job["date_start"], job["date_end"],
        )
    return {"version_id": new_version_id, "run_id": run_id}


import server.researcher.manager as _manager


class InjectMessageBody(BaseModel):
    content: str


@router.post("/{job_id}/start")
async def start_research(job_id: int, request: Request):
    await require_user(request)
    async with get_async_db() as conn:
        job = await conn.fetchrow("SELECT id FROM research_jobs WHERE id=$1", job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Research job not found")
    await _manager.start(job_id)
    return {"ok": True, "job_id": job_id, "status": "active"}


@router.post("/{job_id}/pause")
async def pause_research(job_id: int, request: Request):
    await require_user(request)
    await _manager.pause(job_id)
    return {"ok": True, "job_id": job_id, "status": "paused"}


@router.post("/{job_id}/resume")
async def resume_research(job_id: int, request: Request):
    await require_user(request)
    await _manager.resume(job_id)
    return {"ok": True, "job_id": job_id, "status": "active"}


@router.post("/{job_id}/message", status_code=201)
async def inject_message(job_id: int, body: InjectMessageBody, request: Request):
    await require_user(request)
    async with get_async_db() as conn:
        row = await conn.fetchrow(
            "INSERT INTO research_messages (research_job_id, content) VALUES ($1,$2) RETURNING *",
            job_id, body.content,
        )
        await conn.execute(
            "INSERT INTO research_logs (research_job_id, role, content) VALUES ($1, 'user_inject', $2)",
            job_id, body.content,
        )
    return dict(row)


@router.get("/{job_id}/logs")
async def get_logs(job_id: int, limit: int = 100, offset: int = 0):
    async with get_async_db() as conn:
        rows = await conn.fetch(
            "SELECT * FROM research_logs WHERE research_job_id=$1 ORDER BY created_at ASC, id ASC LIMIT $2 OFFSET $3",
            job_id, limit, offset,
        )
    return [dict(r) for r in rows]


@router.get("/{job_id}/logs/stream")
async def stream_logs(job_id: int):
    async def event_generator():
        conn = await _asyncpg.connect(dsn=os.environ.get("DATABASE_URL", ""))
        queue: asyncio.Queue = asyncio.Queue()

        def _on_notify(conn_ref, pid, channel, payload):
            queue.put_nowait(payload)

        await conn.add_listener("research_log_append", _on_notify)
        try:
            while True:
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=30.0)
                    data = _json.loads(payload)
                    if data.get("job_id") == job_id:
                        async with get_async_db() as db:
                            row = await db.fetchrow("SELECT * FROM research_logs WHERE id=$1", data["log_id"])
                        if row:
                            yield {"event": "log", "data": _json.dumps(dict(row), default=str)}
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": ""}
        finally:
            await conn.remove_listener("research_log_append", _on_notify)
            await conn.close()

    return EventSourceResponse(event_generator())
