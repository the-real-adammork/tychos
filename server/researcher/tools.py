"""Tool definitions and execution for the researcher SDK session.

Each tool maps to an existing research API operation. Execution is async
and talks directly to the DB (not via HTTP) for lower latency.
"""
import hashlib
import json
import math
import asyncio

from server.db import get_async_db
from server.research.allowlist import check_diff_against_allowlist, AllowlistViolation, expand_globs
from server.research.search_engine import run_search

TOOL_SCHEMAS = [
    {
        "name": "propose_params",
        "description": (
            "Propose new parameter values. Validates against the job's allowlist, "
            "creates a new param version, waits for the worker to run the scanner, "
            "and returns the objective + per-eclipse error detail."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "params_json": {
                    "type": "string",
                    "description": "JSON string of the full params dict with your proposed changes",
                },
            },
            "required": ["params_json"],
        },
    },
    {
        "name": "checkpoint",
        "description": "Mark a param version as a checkpoint (best known state). Resets the no-improvement counter.",
        "input_schema": {
            "type": "object",
            "properties": {
                "version_id": {"type": "integer", "description": "The param_version id to checkpoint"},
            },
            "required": ["version_id"],
        },
    },
    {
        "name": "restore",
        "description": (
            "Create a new version from a checkpoint's params and run the scanner. "
            "Use this to revert to a known good state after failed exploration."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "version_id": {"type": "integer", "description": "The checkpoint version_id to restore from"},
            },
            "required": ["version_id"],
        },
    },
    {
        "name": "search",
        "description": (
            "Run server-side Nelder-Mead optimization over 2-6 coupled parameters. "
            "Use when you've identified which params matter and want to grind them mechanically."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "param_keys": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of body.field keys to optimize (e.g. ['sun.start_pos', 'sun.speed'])",
                },
                "budget": {"type": "integer", "description": "Max evaluations (default 20)", "default": 20},
                "scale": {"type": "number", "description": "Initial simplex step fraction (default 0.01)", "default": 0.01},
            },
            "required": ["param_keys"],
        },
    },
]


async def execute_tool(tool_name: str, tool_input: dict, job_id: int) -> str:
    """Execute a tool and return a JSON string result for the SDK."""
    try:
        if tool_name == "propose_params":
            return await _propose_params(job_id, tool_input["params_json"])
        elif tool_name == "checkpoint":
            return await _checkpoint(job_id, tool_input["version_id"])
        elif tool_name == "restore":
            return await _restore(job_id, tool_input["version_id"])
        elif tool_name == "search":
            return await _search(
                job_id,
                tool_input["param_keys"],
                tool_input.get("budget", 20),
                tool_input.get("scale", 0.01),
            )
        else:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


async def _get_job(conn, job_id: int):
    return await conn.fetchrow("SELECT * FROM research_jobs WHERE id=$1", job_id)


async def _get_baseline(conn, param_set_id: int) -> dict:
    row = await conn.fetchrow(
        "SELECT params_json FROM param_versions WHERE param_set_id=$1 AND is_checkpoint=TRUE ORDER BY version_number DESC LIMIT 1",
        param_set_id,
    )
    if row is None:
        row = await conn.fetchrow(
            "SELECT params_json FROM param_versions WHERE param_set_id=$1 ORDER BY version_number ASC LIMIT 1",
            param_set_id,
        )
    return json.loads(row["params_json"])


async def _wait_for_run(run_id: int, timeout: float = 300.0) -> str:
    """Poll until run is done or failed. Returns status string."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        async with get_async_db() as conn:
            row = await conn.fetchrow("SELECT status FROM runs WHERE id=$1", run_id)
        if row and row["status"] in ("done", "failed"):
            return row["status"]
        await asyncio.sleep(2.0)
    return "timeout"


async def _get_view_result(run_id: int, view_name: str, full_detail: bool = False) -> dict:
    """Query the view for a completed run. Returns {objective, n_scored, detail}."""
    async with get_async_db() as conn:
        run = await conn.fetchrow("SELECT date_start, date_end FROM runs WHERE id=$1", run_id)
        filters = ["run_id = $1"]
        args: list = [run_id]
        if run["date_start"]:
            filters.append(f"date >= ${len(args)+1}")
            args.append(run["date_start"])
        if run["date_end"]:
            filters.append(f"date <= ${len(args)+1}")
            args.append(run["date_end"])
        where = " AND ".join(filters)
        obj = await conn.fetchrow(
            f"SELECT AVG(error) AS objective, COUNT(*) AS n FROM {view_name} WHERE {where}", *args
        )
        if full_detail:
            rows = await conn.fetch(f"SELECT * FROM {view_name} WHERE {where} ORDER BY error DESC", *args)
        else:
            rows = await conn.fetch(f"SELECT * FROM {view_name} WHERE {where} ORDER BY error DESC LIMIT 10", *args)
    return {
        "objective": float(obj["objective"]) if obj["objective"] is not None else None,
        "n_scored": int(obj["n"]),
        "detail": [dict(r) for r in rows],
    }


async def _propose_params(job_id: int, params_json_str: str) -> str:
    async with get_async_db() as conn:
        job = await _get_job(conn, job_id)
        baseline = await _get_baseline(conn, job["param_set_id"])

        try:
            new_params = json.loads(params_json_str)
        except Exception as exc:
            return json.dumps({"error": f"Invalid JSON: {exc}"})

        try:
            check_diff_against_allowlist(
                new_params, baseline,
                allowlist_globs=list(job["allowlist"]),
                known_bodies=list(baseline.keys()),
            )
        except AllowlistViolation as exc:
            return json.dumps({"error": f"Allowlist violation: {exc}"})

        latest_num = await conn.fetchval(
            "SELECT COALESCE(MAX(version_number),0) FROM param_versions WHERE param_set_id=$1",
            job["param_set_id"],
        )
        md5 = hashlib.md5(json.dumps(new_params, sort_keys=True).encode()).hexdigest()
        version_id = await conn.fetchval(
            "INSERT INTO param_versions (param_set_id, version_number, params_md5, params_json, notes) "
            "VALUES ($1,$2,$3,$4,$5) RETURNING id",
            job["param_set_id"], latest_num + 1, md5, params_json_str, "researcher agent iteration",
        )
        run_id = await conn.fetchval(
            "INSERT INTO runs (param_version_id, dataset_id, status, date_start, date_end) "
            "VALUES ($1,$2,'queued',$3,$4) RETURNING id",
            version_id, job["dataset_id"], job["date_start"], job["date_end"],
        )

    status = await _wait_for_run(run_id)
    if status != "done":
        return json.dumps({"error": f"Run {run_id} {status}", "version_id": version_id, "run_id": run_id})

    view = await _get_view_result(run_id, job["view_name"], full_detail=False)
    return json.dumps({
        "version_id": version_id,
        "run_id": run_id,
        **view,
    })


async def _checkpoint(job_id: int, version_id: int) -> str:
    async with get_async_db() as conn:
        job = await _get_job(conn, job_id)
        v = await conn.fetchrow(
            "SELECT id FROM param_versions WHERE id=$1 AND param_set_id=$2",
            version_id, job["param_set_id"],
        )
        if not v:
            return json.dumps({"error": f"Version {version_id} not found on this job's param set"})
        await conn.execute("UPDATE param_versions SET is_checkpoint=TRUE WHERE id=$1", version_id)

    view = await _get_view_result_for_version(version_id, job["view_name"])
    return json.dumps({"ok": True, "version_id": version_id, **(view or {})})


async def _get_view_result_for_version(version_id: int, view_name: str) -> dict | None:
    """Get full view detail for the latest done run of a version."""
    async with get_async_db() as conn:
        run = await conn.fetchrow(
            "SELECT id FROM runs WHERE param_version_id=$1 AND status='done' ORDER BY completed_at DESC LIMIT 1",
            version_id,
        )
    if not run:
        return None
    return await _get_view_result(run["id"], view_name, full_detail=True)


async def _restore(job_id: int, version_id: int) -> str:
    async with get_async_db() as conn:
        job = await _get_job(conn, job_id)
        src = await conn.fetchrow(
            "SELECT params_json FROM param_versions WHERE id=$1 AND param_set_id=$2",
            version_id, job["param_set_id"],
        )
        if not src:
            return json.dumps({"error": f"Version {version_id} not found on this job's param set"})
        params_json = src["params_json"]
        md5 = hashlib.md5(json.dumps(json.loads(params_json), sort_keys=True).encode()).hexdigest()
        latest_num = await conn.fetchval(
            "SELECT COALESCE(MAX(version_number),0) FROM param_versions WHERE param_set_id=$1",
            job["param_set_id"],
        )
        new_vid = await conn.fetchval(
            "INSERT INTO param_versions (param_set_id, version_number, parent_version_id, params_md5, params_json, notes) "
            "VALUES ($1,$2,$3,$4,$5,$6) RETURNING id",
            job["param_set_id"], latest_num + 1, version_id, md5, params_json, f"restored from v{version_id}",
        )
        run_id = await conn.fetchval(
            "INSERT INTO runs (param_version_id, dataset_id, status, date_start, date_end) "
            "VALUES ($1,$2,'queued',$3,$4) RETURNING id",
            new_vid, job["dataset_id"], job["date_start"], job["date_end"],
        )

    status = await _wait_for_run(run_id)
    if status != "done":
        return json.dumps({"error": f"Run {run_id} {status}", "version_id": new_vid, "run_id": run_id})

    view = await _get_view_result(run_id, job["view_name"], full_detail=True)
    return json.dumps({"version_id": new_vid, "run_id": run_id, **view})


async def _search(job_id: int, param_keys: list[str], budget: int, scale: float) -> str:
    async with get_async_db() as conn:
        job = await _get_job(conn, job_id)
        baseline = await _get_baseline(conn, job["param_set_id"])
        allowed = expand_globs(list(job["allowlist"]), list(baseline.keys()))
        forbidden = [k for k in param_keys if k not in allowed]
        if forbidden:
            return json.dumps({"error": f"param_keys not in allowlist: {forbidden}"})

        ds = await conn.fetchrow("SELECT slug, scan_window_hours FROM datasets WHERE id=$1", job["dataset_id"])
        jpl_rows = await conn.fetch(
            "SELECT julian_day_tt, best_jd, sun_ra_rad, sun_dec_rad, moon_ra_rad, moon_dec_rad "
            "FROM jpl_reference WHERE dataset_id=$1",
            job["dataset_id"],
        )
        cat_filters = ["dataset_id=$1"]
        cat_args: list = [job["dataset_id"]]
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

    from server.services.scanner import scan_solar_eclipses, scan_lunar_eclipses

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
                errs.append(math.sqrt(s_dra**2 + s_ddec**2))
            else:
                m_dra = (r["tychos_moon_ra_at_jpl_rad"] - jpl["moon_ra_rad"]) * cos_m * RAD_TO_ARCMIN
                m_ddec = (r["tychos_moon_dec_at_jpl_rad"] - jpl["moon_dec_rad"]) * RAD_TO_ARCMIN
                if job["view_name"] == "v_moon_position":
                    errs.append(math.sqrt(m_dra**2 + m_ddec**2))
                else:
                    errs.append(math.sqrt(s_dra**2 + s_ddec**2 + m_dra**2 + m_ddec**2))
        return float("inf") if not errs else sum(errs) / len(errs)

    search_result = await asyncio.to_thread(
        run_search,
        current=baseline,
        param_keys=param_keys,
        evaluate=_evaluate,
        budget=budget,
        scale=scale,
    )

    improved = search_result.best_objective < search_result.starting_objective
    winner_version_id = None
    winner_run_id = None

    if improved:
        async with get_async_db() as conn:
            latest_num = await conn.fetchval(
                "SELECT COALESCE(MAX(version_number),0) FROM param_versions WHERE param_set_id=$1",
                job["param_set_id"],
            )
            pj = json.dumps(search_result.best_params, sort_keys=True)
            md5 = hashlib.md5(pj.encode()).hexdigest()
            winner_version_id = await conn.fetchval(
                "INSERT INTO param_versions (param_set_id, version_number, params_md5, params_json, notes, is_checkpoint) "
                "VALUES ($1,$2,$3,$4,$5,TRUE) RETURNING id",
                job["param_set_id"], latest_num + 1, md5, pj,
                f"search winner: {param_keys} (budget {budget})",
            )
            winner_run_id = await conn.fetchval(
                "INSERT INTO runs (param_version_id, dataset_id, status, date_start, date_end) "
                "VALUES ($1,$2,'queued',$3,$4) RETURNING id",
                winner_version_id, job["dataset_id"], job["date_start"], job["date_end"],
            )

    return json.dumps({
        "starting_objective": search_result.starting_objective,
        "best_objective": search_result.best_objective,
        "delta": search_result.best_objective - search_result.starting_objective,
        "improved": improved,
        "n_evals": search_result.n_evals,
        "winner_version_id": winner_version_id,
        "winner_run_id": winner_run_id,
    })
