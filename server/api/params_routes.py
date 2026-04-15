"""Param set routes: CRUD + fork + versioning."""
import hashlib
import json

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from server.auth import require_user
from server.db import get_async_db
from server.params_store import save_param_set, save_param_version

router = APIRouter(prefix="/api/params")


def _compute_md5(params_json: str) -> str:
    return hashlib.md5(
        json.dumps(json.loads(params_json), sort_keys=True).encode()
    ).hexdigest()


def _row_to_dict(row) -> dict:
    return dict(row)


async def auto_queue_runs(conn, param_version_id: int, date_start: str | None = None, date_end: str | None = None):
    """Queue a run for each dataset for a new param version."""
    ds_rows = await conn.fetch("SELECT id FROM datasets ORDER BY id")
    for ds in ds_rows:
        await conn.execute(
            "INSERT INTO runs (param_version_id, dataset_id, status, date_start, date_end) "
            "VALUES ($1,$2,'queued',$3,$4)",
            param_version_id, ds["id"], date_start, date_end,
        )


@router.get("")
async def list_param_sets():
    """List all param sets with owner info and latest version detection rates."""
    async with get_async_db() as conn:
        rows = await conn.fetch(
            """
            SELECT ps.*, u.name AS owner_name, u.email AS owner_email
            FROM param_sets ps
            JOIN users u ON ps.owner_id = u.id
            ORDER BY ps.created_at DESC
            """
        )

        result = []
        for row in rows:
            item = _row_to_dict(row)

            # Resolve forked_from name
            if item.get("forked_from_id"):
                fork_row = await conn.fetchrow(
                    "SELECT name FROM param_sets WHERE id = $1",
                    item["forked_from_id"],
                )
                item["forked_from_name"] = fork_row["name"] if fork_row else None
            else:
                item["forked_from_name"] = None

            # Find latest version
            ver_row = await conn.fetchrow(
                """
                SELECT id FROM param_versions
                WHERE param_set_id = $1
                ORDER BY version_number DESC
                LIMIT 1
                """,
                item["id"],
            )

            if ver_row:
                latest_version_id = ver_row["id"]
                # Latest done runs for latest version (one per dataset)
                run_rows = await conn.fetch(
                    """
                    SELECT r.id, r.dataset_id, d.slug AS dataset_slug, r.status, r.total_eclipses, r.detected, r.completed_at
                    FROM runs r
                    JOIN datasets d ON r.dataset_id = d.id
                    WHERE r.param_version_id = $1 AND r.status = 'done'
                    ORDER BY r.completed_at DESC
                    """,
                    latest_version_id,
                )
                latest_runs = []
                for rr in run_rows:
                    rd = _row_to_dict(rr)
                    mean_err = await conn.fetchval(
                        "SELECT AVG(tychos_error_arcmin) FROM eclipse_results WHERE run_id = $1",
                        rd["id"],
                    )
                    rd["mean_tychos_error"] = round(mean_err, 2) if mean_err is not None else None
                    latest_runs.append(rd)
                item["latest_runs"] = latest_runs
            else:
                item["latest_runs"] = []

            result.append(item)

    return result


class CreateParamSetBody(BaseModel):
    name: str
    description: str | None = None
    params_json: str
    notes: str | None = None


@router.post("", status_code=201)
async def create_param_set(body: CreateParamSetBody, request: Request):
    """Create a new param set + first version + auto-queue solar & lunar runs. Auth required."""
    user = await require_user(request)

    if not body.name or not body.name.strip():
        raise HTTPException(status_code=422, detail="name is required")
    if not body.params_json or not body.params_json.strip():
        raise HTTPException(status_code=422, detail="params_json is required")

    try:
        params_md5 = _compute_md5(body.params_json)
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"params_json is not valid JSON: {exc}")

    async with get_async_db() as conn:
        # Create param set (no params_json/params_md5 on the set itself)
        param_set_id = await conn.fetchval(
            """
            INSERT INTO param_sets (name, description, owner_id)
            VALUES ($1, $2, $3) RETURNING id
            """,
            body.name.strip(), body.description, user["id"],
        )

        # Create first version
        param_version_id = await conn.fetchval(
            """
            INSERT INTO param_versions (param_set_id, version_number, params_md5, params_json, notes)
            VALUES ($1, 1, $2, $3, $4) RETURNING id
            """,
            param_set_id, params_md5, body.params_json, body.notes,
        )

        # Auto-queue solar and lunar runs
        await auto_queue_runs(conn, param_version_id)

        row = await conn.fetchrow(
            """
            SELECT ps.*, u.name AS owner_name, u.email AS owner_email
            FROM param_sets ps
            JOIN users u ON ps.owner_id = u.id
            WHERE ps.id = $1
            """,
            param_set_id,
        )

    # Persist to disk
    save_param_set(body.name.strip(), body.description)
    save_param_version(
        body.name.strip(), 1,
        json.loads(body.params_json),
        notes=body.notes,
    )

    return _row_to_dict(row)


@router.get("/{param_set_id}")
async def get_param_set(param_set_id: int):
    """Get a single param set with owner info, all versions, and latest version's runs."""
    async with get_async_db() as conn:
        row = await conn.fetchrow(
            """
            SELECT ps.*, u.name AS owner_name, u.email AS owner_email
            FROM param_sets ps
            JOIN users u ON ps.owner_id = u.id
            WHERE ps.id = $1
            """,
            param_set_id,
        )

        if row is None:
            raise HTTPException(status_code=404, detail="Param set not found")

        item = _row_to_dict(row)

        # All versions (newest first)
        ver_rows = await conn.fetch(
            """
            SELECT id, version_number, parent_version_id, created_at, params_md5, notes
            FROM param_versions
            WHERE param_set_id = $1
            ORDER BY version_number DESC
            """,
            param_set_id,
        )
        versions = [_row_to_dict(v) for v in ver_rows]
        item["versions"] = versions

        # Best detection across ALL versions
        version_ids = [v["id"] for v in versions]
        if version_ids:
            # Build $-placeholders for version_ids IN clause
            placeholders = ",".join(f"${i+1}" for i in range(len(version_ids)))
            ds_placeholder = f"${len(version_ids)+1}"

            ds_rows = await conn.fetch("SELECT id, slug FROM datasets ORDER BY id")
            for ds in ds_rows:
                best_row = await conn.fetchrow(
                    f"""
                    SELECT r.id AS run_id, r.total_eclipses, pv.version_number,
                           AVG(er.tychos_error_arcmin) AS mean_error
                    FROM runs r
                    JOIN param_versions pv ON r.param_version_id = pv.id
                    JOIN eclipse_results er ON er.run_id = r.id
                    WHERE r.param_version_id IN ({placeholders})
                      AND r.dataset_id = {ds_placeholder} AND r.status = 'done'
                      AND r.total_eclipses > 0
                      AND er.tychos_error_arcmin IS NOT NULL
                    GROUP BY r.id, pv.version_number
                    ORDER BY mean_error ASC
                    LIMIT 1
                    """,
                    *version_ids, ds["id"],
                )
                if best_row:
                    item[f"{ds['slug']}_stats"] = {
                        "mean_tychos_error": round(best_row["mean_error"], 2) if best_row["mean_error"] is not None else None,
                        "total_eclipses": best_row["total_eclipses"],
                        "version_number": best_row["version_number"],
                    }
                else:
                    item[f"{ds['slug']}_stats"] = None

            # All runs for latest version
            latest_version_id = versions[0]["id"]
            runs_rows = await conn.fetch(
                """
                SELECT r.id, r.dataset_id, d.slug AS dataset_slug, d.name AS dataset_name,
                       r.status, r.total_eclipses, r.detected, r.created_at, r.completed_at
                FROM runs r
                JOIN datasets d ON r.dataset_id = d.id
                WHERE r.param_version_id = $1
                ORDER BY r.created_at DESC
                """,
                latest_version_id,
            )
            item["latest_version_runs"] = [_row_to_dict(r) for r in runs_rows]
        else:
            item["solar_eclipse_stats"] = None
            item["lunar_eclipse_stats"] = None
            item["latest_version_runs"] = []

    return item


class UpdateParamSetBody(BaseModel):
    name: str | None = None
    description: str | None = None
    params_json: str | None = None
    parent_version_id: int | None = None  # which version this edit is based on
    notes: str | None = None


@router.put("/{param_set_id}")
async def update_param_set(param_set_id: int, body: UpdateParamSetBody, request: Request):
    """Partial update. If params_json changes md5, creates a new version + queues runs. Auth required; owner only."""
    user = await require_user(request)

    async with get_async_db() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM param_sets WHERE id = $1", param_set_id
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Param set not found")
        if row["owner_id"] != user["id"]:
            raise HTTPException(status_code=403, detail="Not the owner")

        # Update name/description if provided
        meta_updates: dict = {}
        if body.name is not None:
            meta_updates["name"] = body.name.strip()
        if body.description is not None:
            meta_updates["description"] = body.description

        if meta_updates:
            set_parts = []
            values = []
            i = 1
            for k, v in meta_updates.items():
                set_parts.append(f"{k} = ${i}")
                values.append(v)
                i += 1
            values.append(param_set_id)
            await conn.execute(
                f"UPDATE param_sets SET {', '.join(set_parts)} WHERE id = ${i}",
                *values,
            )

        # Handle params_json: create new version only if md5 differs from latest
        new_version_id = None
        if body.params_json is not None:
            try:
                new_md5 = _compute_md5(body.params_json)
            except (json.JSONDecodeError, ValueError) as exc:
                raise HTTPException(
                    status_code=422, detail=f"params_json is not valid JSON: {exc}"
                )

            latest_ver = await conn.fetchrow(
                """
                SELECT id, version_number, params_md5
                FROM param_versions
                WHERE param_set_id = $1
                ORDER BY version_number DESC
                LIMIT 1
                """,
                param_set_id,
            )

            if latest_ver is None or latest_ver["params_md5"] != new_md5:
                next_version = (latest_ver["version_number"] + 1) if latest_ver else 1
                # parent_version_id: explicitly provided, or default to latest
                parent_id = body.parent_version_id
                if parent_id is None and latest_ver is not None:
                    parent_id = latest_ver["id"]
                param_version_id = await conn.fetchval(
                    """
                    INSERT INTO param_versions (param_set_id, version_number, parent_version_id, params_md5, params_json, notes)
                    VALUES ($1, $2, $3, $4, $5, $6) RETURNING id
                    """,
                    param_set_id, next_version, parent_id, new_md5, body.params_json, body.notes,
                )
                new_version_id = param_version_id
                await auto_queue_runs(conn, param_version_id)

                # Persist new version to disk
                parent_label = None
                if parent_id:
                    par_row = await conn.fetchrow(
                        "SELECT pv.version_number, ps.name FROM param_versions pv JOIN param_sets ps ON pv.param_set_id = ps.id WHERE pv.id = $1",
                        parent_id,
                    )
                    if par_row:
                        parent_label = f"{par_row['name']}/v{par_row['version_number']}"

                ps_name_row = await conn.fetchrow(
                    "SELECT name FROM param_sets WHERE id = $1", param_set_id
                )
                save_param_version(
                    ps_name_row["name"], next_version,
                    json.loads(body.params_json),
                    notes=body.notes,
                    parent_version=parent_label,
                )

        updated = await conn.fetchrow(
            """
            SELECT ps.*, u.name AS owner_name, u.email AS owner_email
            FROM param_sets ps
            JOIN users u ON ps.owner_id = u.id
            WHERE ps.id = $1
            """,
            param_set_id,
        )

    result = _row_to_dict(updated)
    if new_version_id is not None:
        result["new_version_id"] = new_version_id
    return result


@router.delete("/{param_set_id}", status_code=204)
async def delete_param_set(param_set_id: int, request: Request):
    """Delete a param set. Auth required; owner only."""
    user = await require_user(request)

    async with get_async_db() as conn:
        row = await conn.fetchrow(
            "SELECT owner_id FROM param_sets WHERE id = $1", param_set_id
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Param set not found")
        if row["owner_id"] != user["id"]:
            raise HTTPException(status_code=403, detail="Not the owner")

        await conn.execute("DELETE FROM param_sets WHERE id = $1", param_set_id)


@router.delete("/{param_set_id}/versions/{version_id}", status_code=204)
async def delete_param_version(param_set_id: int, version_id: int, request: Request):
    """Delete a single version of a param set. Auth required; owner only.

    Refuses to delete the last remaining version of a set (delete the whole
    param set instead). Re-parents any child versions to this version's parent
    so the version chain stays intact. Cascades to runs and eclipse_results
    via the existing FK ON DELETE CASCADE.
    """
    user = await require_user(request)

    async with get_async_db() as conn:
        # Verify ownership and existence
        ps_row = await conn.fetchrow(
            "SELECT owner_id FROM param_sets WHERE id = $1", param_set_id
        )
        if ps_row is None:
            raise HTTPException(status_code=404, detail="Param set not found")
        if ps_row["owner_id"] != user["id"]:
            raise HTTPException(status_code=403, detail="Not the owner")

        ver_row = await conn.fetchrow(
            "SELECT id, parent_version_id FROM param_versions WHERE id = $1 AND param_set_id = $2",
            version_id, param_set_id,
        )
        if ver_row is None:
            raise HTTPException(status_code=404, detail="Version not found in this param set")

        # Refuse to delete the last remaining version
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM param_versions WHERE param_set_id = $1",
            param_set_id,
        )
        if count <= 1:
            raise HTTPException(
                status_code=409,
                detail="Cannot delete the only version of a param set. Delete the param set instead.",
            )

        # Re-parent any child versions to this version's parent so the chain stays intact
        await conn.execute(
            "UPDATE param_versions SET parent_version_id = $1 WHERE parent_version_id = $2",
            ver_row["parent_version_id"], version_id,
        )

        # Delete the version (runs + eclipse_results cascade via FK)
        await conn.execute("DELETE FROM param_versions WHERE id = $1", version_id)


class ForkBody(BaseModel):
    name: str | None = None


@router.post("/{param_set_id}/fork", status_code=201)
async def fork_param_set(param_set_id: int, request: Request, body: ForkBody = ForkBody()):
    """Fork a param set: copy latest version into a new ParamSet + ParamVersion + auto-queue runs. Auth required."""
    user = await require_user(request)

    async with get_async_db() as conn:
        source = await conn.fetchrow(
            "SELECT * FROM param_sets WHERE id = $1", param_set_id
        )
        if source is None:
            raise HTTPException(status_code=404, detail="Param set not found")

        # Get latest version's params
        latest_ver = await conn.fetchrow(
            """
            SELECT version_number, params_json, params_md5
            FROM param_versions
            WHERE param_set_id = $1
            ORDER BY version_number DESC
            LIMIT 1
            """,
            param_set_id,
        )
        if latest_ver is None:
            raise HTTPException(status_code=404, detail="Source param set has no versions")

        fork_name = body.name or f"{source['name']} (fork)"

        new_param_set_id = await conn.fetchval(
            """
            INSERT INTO param_sets (name, description, owner_id, forked_from_id)
            VALUES ($1, $2, $3, $4) RETURNING id
            """,
            fork_name, source["description"], user["id"], param_set_id,
        )

        param_version_id = await conn.fetchval(
            """
            INSERT INTO param_versions (param_set_id, version_number, params_md5, params_json)
            VALUES ($1, 1, $2, $3) RETURNING id
            """,
            new_param_set_id, latest_ver["params_md5"], latest_ver["params_json"],
        )

        await auto_queue_runs(conn, param_version_id)

        row = await conn.fetchrow(
            """
            SELECT ps.*, u.name AS owner_name, u.email AS owner_email
            FROM param_sets ps
            JOIN users u ON ps.owner_id = u.id
            WHERE ps.id = $1
            """,
            new_param_set_id,
        )

    # Persist fork to disk
    save_param_set(fork_name, source["description"], forked_from=source["name"])
    save_param_version(
        fork_name, 1,
        json.loads(latest_ver["params_json"]),
        parent_version=f"{source['name']}/v{latest_ver['version_number']}",
    )

    return _row_to_dict(row)


@router.get("/{param_set_id}/versions")
async def list_versions(param_set_id: int):
    """List all versions for a param set."""
    async with get_async_db() as conn:
        ps_row = await conn.fetchrow(
            "SELECT id FROM param_sets WHERE id = $1", param_set_id
        )
        if ps_row is None:
            raise HTTPException(status_code=404, detail="Param set not found")

        rows = await conn.fetch(
            """
            SELECT id, version_number, parent_version_id, params_md5, created_at
            FROM param_versions
            WHERE param_set_id = $1
            ORDER BY version_number DESC
            """,
            param_set_id,
        )

    return [_row_to_dict(r) for r in rows]


@router.get("/{param_set_id}/versions/{version_id}")
async def get_version(param_set_id: int, version_id: int):
    """Get a specific version detail with its runs."""
    async with get_async_db() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, version_number, parent_version_id, params_md5, params_json, notes, created_at
            FROM param_versions
            WHERE id = $1 AND param_set_id = $2
            """,
            version_id, param_set_id,
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Version not found")

        item = _row_to_dict(row)

        runs_rows = await conn.fetch(
            """
            SELECT r.id, r.dataset_id, d.slug AS dataset_slug, d.name AS dataset_name,
                   r.status, r.total_eclipses, r.detected, r.created_at, r.completed_at
            FROM runs r
            JOIN datasets d ON r.dataset_id = d.id
            WHERE r.param_version_id = $1
            ORDER BY r.created_at DESC
            """,
            version_id,
        )
        runs_list = [_row_to_dict(r) for r in runs_rows]

        # Compute mean_tychos_error for each done run
        for run in runs_list:
            if run["status"] == "done":
                mean_err = await conn.fetchval(
                    """
                    SELECT AVG(tychos_error_arcmin)
                    FROM eclipse_results WHERE run_id = $1
                    """,
                    run["id"],
                )
                run["mean_tychos_error"] = round(mean_err, 2) if mean_err is not None else None
            else:
                run["mean_tychos_error"] = None

        item["runs"] = runs_list

        # Walk ancestor chain
        ancestors = []
        current_parent_id = item.get("parent_version_id")
        seen = set()
        while current_parent_id and current_parent_id not in seen:
            seen.add(current_parent_id)
            anc_row = await conn.fetchrow(
                """
                SELECT pv.id, pv.version_number, pv.parent_version_id, pv.params_md5, pv.params_json, pv.notes, pv.created_at
                FROM param_versions pv
                WHERE pv.id = $1
                """,
                current_parent_id,
            )
            if not anc_row:
                break
            anc = _row_to_dict(anc_row)

            # Get detection stats for this ancestor
            ds_rows2 = await conn.fetch("SELECT id, slug FROM datasets ORDER BY id")
            for ds in ds_rows2:
                stat_row = await conn.fetchrow(
                    """
                    SELECT detected, total_eclipses FROM runs
                    WHERE param_version_id = $1 AND dataset_id = $2 AND status = 'done'
                    ORDER BY completed_at DESC LIMIT 1
                    """,
                    current_parent_id, ds["id"],
                )
                if stat_row:
                    anc[f"{ds['slug']}_detected"] = stat_row["detected"]
                    anc[f"{ds['slug']}_total"] = stat_row["total_eclipses"]
                else:
                    anc[f"{ds['slug']}_detected"] = None
                    anc[f"{ds['slug']}_total"] = None

            ancestors.append(anc)
            current_parent_id = anc_row["parent_version_id"]

        item["ancestors"] = ancestors

    return item


class UpdateVersionNotesBody(BaseModel):
    notes: str | None = None


@router.patch("/{param_set_id}/versions/{version_id}")
async def update_version_notes(param_set_id: int, version_id: int, body: UpdateVersionNotesBody, request: Request):
    """Update only the notes on an existing version. Does not create a new version."""
    user = await require_user(request)

    async with get_async_db() as conn:
        row = await conn.fetchrow(
            """
            SELECT pv.id, ps.owner_id
            FROM param_versions pv
            JOIN param_sets ps ON pv.param_set_id = ps.id
            WHERE pv.id = $1 AND pv.param_set_id = $2
            """,
            version_id, param_set_id,
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Version not found")
        if row["owner_id"] != user["id"]:
            raise HTTPException(status_code=403, detail="Not the owner")

        await conn.execute(
            "UPDATE param_versions SET notes = $1 WHERE id = $2",
            body.notes, version_id,
        )

        # Update the version file on disk
        ver_row = await conn.fetchrow(
            "SELECT pv.version_number, pv.params_json, pv.parent_version_id, ps.name AS ps_name FROM param_versions pv JOIN param_sets ps ON pv.param_set_id = ps.id WHERE pv.id = $1",
            version_id,
        )
        if ver_row:
            parent_label = None
            if ver_row["parent_version_id"]:
                par_row = await conn.fetchrow(
                    "SELECT pv.version_number, ps.name FROM param_versions pv JOIN param_sets ps ON pv.param_set_id = ps.id WHERE pv.id = $1",
                    ver_row["parent_version_id"],
                )
                if par_row:
                    parent_label = f"{par_row['name']}/v{par_row['version_number']}"

            save_param_version(
                ver_row["ps_name"], ver_row["version_number"],
                json.loads(ver_row["params_json"]),
                notes=body.notes,
                parent_version=parent_label,
            )

    return {"ok": True}
