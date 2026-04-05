"""Param set routes: CRUD + fork + versioning."""
import hashlib
import json

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from server.auth import require_user
from server.db import get_async_db

router = APIRouter(prefix="/api/params")


def _compute_md5(params_json: str) -> str:
    return hashlib.md5(
        json.dumps(json.loads(params_json), sort_keys=True).encode()
    ).hexdigest()


def _row_to_dict(row) -> dict:
    return dict(row)


async def auto_queue_runs(conn, param_version_id: int):
    """Queue solar and lunar runs for a new param version."""
    for test_type in ("solar", "lunar"):
        await conn.execute(
            "INSERT INTO runs (param_version_id, test_type, status) VALUES (?, ?, 'queued')",
            (param_version_id, test_type),
        )
    await conn.commit()


@router.get("")
async def list_param_sets():
    """List all param sets with owner info and latest version detection rates."""
    async with get_async_db() as conn:
        cursor = await conn.execute(
            """
            SELECT ps.*, u.name AS owner_name, u.email AS owner_email
            FROM param_sets ps
            JOIN users u ON ps.owner_id = u.id
            ORDER BY ps.created_at DESC
            """
        )
        rows = await cursor.fetchall()

        result = []
        for row in rows:
            item = _row_to_dict(row)

            # Resolve forked_from name
            if item.get("forked_from_id"):
                fork_cursor = await conn.execute(
                    "SELECT name FROM param_sets WHERE id = ?",
                    (item["forked_from_id"],),
                )
                fork_row = await fork_cursor.fetchone()
                item["forked_from_name"] = fork_row["name"] if fork_row else None
            else:
                item["forked_from_name"] = None

            # Find latest version
            ver_cursor = await conn.execute(
                """
                SELECT id FROM param_versions
                WHERE param_set_id = ?
                ORDER BY version_number DESC
                LIMIT 1
                """,
                (item["id"],),
            )
            ver_row = await ver_cursor.fetchone()

            if ver_row:
                latest_version_id = ver_row["id"]
                # Latest done runs for latest version (one per test_type)
                run_cursor = await conn.execute(
                    """
                    SELECT id, test_type, status, total_eclipses, detected, completed_at
                    FROM runs
                    WHERE param_version_id = ? AND status = 'done'
                    ORDER BY completed_at DESC
                    """,
                    (latest_version_id,),
                )
                run_rows = await run_cursor.fetchall()
                item["latest_runs"] = [_row_to_dict(r) for r in run_rows]
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
        ps_cursor = await conn.execute(
            """
            INSERT INTO param_sets (name, description, owner_id)
            VALUES (?, ?, ?)
            """,
            (body.name.strip(), body.description, user["id"]),
        )
        param_set_id = ps_cursor.lastrowid

        # Create first version
        pv_cursor = await conn.execute(
            """
            INSERT INTO param_versions (param_set_id, version_number, params_md5, params_json, notes)
            VALUES (?, 1, ?, ?, ?)
            """,
            (param_set_id, params_md5, body.params_json, body.notes),
        )
        param_version_id = pv_cursor.lastrowid
        await conn.commit()

        # Auto-queue solar and lunar runs
        await auto_queue_runs(conn, param_version_id)

        row_cursor = await conn.execute(
            """
            SELECT ps.*, u.name AS owner_name, u.email AS owner_email
            FROM param_sets ps
            JOIN users u ON ps.owner_id = u.id
            WHERE ps.id = ?
            """,
            (param_set_id,),
        )
        row = await row_cursor.fetchone()

    return _row_to_dict(row)


@router.get("/{param_set_id}")
async def get_param_set(param_set_id: int):
    """Get a single param set with owner info, all versions, and latest version's runs."""
    async with get_async_db() as conn:
        cursor = await conn.execute(
            """
            SELECT ps.*, u.name AS owner_name, u.email AS owner_email
            FROM param_sets ps
            JOIN users u ON ps.owner_id = u.id
            WHERE ps.id = ?
            """,
            (param_set_id,),
        )
        row = await cursor.fetchone()

        if row is None:
            raise HTTPException(status_code=404, detail="Param set not found")

        item = _row_to_dict(row)

        # All versions (newest first)
        ver_cursor = await conn.execute(
            """
            SELECT id, version_number, parent_version_id, created_at, params_md5, notes
            FROM param_versions
            WHERE param_set_id = ?
            ORDER BY version_number DESC
            """,
            (param_set_id,),
        )
        versions = [_row_to_dict(v) for v in await ver_cursor.fetchall()]
        item["versions"] = versions

        # Best detection across ALL versions
        version_ids = [v["id"] for v in versions]
        if version_ids:
            placeholders = ",".join("?" * len(version_ids))

            for test_type in ("solar", "lunar"):
                # Find best overall pass rate across all versions
                best_cursor = await conn.execute(
                    f"""
                    SELECT r.id AS run_id, r.total_eclipses, pv.version_number,
                           SUM(CASE WHEN er.detected = 1 OR (er.moon_error_arcmin IS NOT NULL AND er.moon_error_arcmin < 60) THEN 1 ELSE 0 END) AS overall_pass
                    FROM runs r
                    JOIN param_versions pv ON r.param_version_id = pv.id
                    JOIN eclipse_results er ON er.run_id = r.id
                    WHERE r.param_version_id IN ({placeholders})
                      AND r.test_type = ? AND r.status = 'done'
                      AND r.total_eclipses > 0
                    GROUP BY r.id
                    ORDER BY CAST(overall_pass AS REAL) / r.total_eclipses DESC
                    LIMIT 1
                    """,
                    (*version_ids, test_type),
                )
                best_row = await best_cursor.fetchone()
                if best_row:
                    item[f"{test_type}_stats"] = {
                        "overall_pass": best_row["overall_pass"],
                        "total_eclipses": best_row["total_eclipses"],
                        "version_number": best_row["version_number"],
                    }
                else:
                    item[f"{test_type}_stats"] = None

            # All runs for latest version
            latest_version_id = versions[0]["id"]
            runs_cursor = await conn.execute(
                """
                SELECT id, test_type, status, total_eclipses, detected, created_at, completed_at
                FROM runs
                WHERE param_version_id = ?
                ORDER BY created_at DESC
                """,
                (latest_version_id,),
            )
            item["latest_version_runs"] = [
                _row_to_dict(r) for r in await runs_cursor.fetchall()
            ]
        else:
            item["solar_stats"] = None
            item["lunar_stats"] = None
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
        cursor = await conn.execute(
            "SELECT * FROM param_sets WHERE id = ?", (param_set_id,)
        )
        row = await cursor.fetchone()
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
            set_clause = ", ".join(f"{k} = ?" for k in meta_updates)
            values = list(meta_updates.values()) + [param_set_id]
            await conn.execute(
                f"UPDATE param_sets SET {set_clause} WHERE id = ?", values
            )
            await conn.commit()

        # Handle params_json: create new version only if md5 differs from latest
        new_version_id = None
        if body.params_json is not None:
            try:
                new_md5 = _compute_md5(body.params_json)
            except (json.JSONDecodeError, ValueError) as exc:
                raise HTTPException(
                    status_code=422, detail=f"params_json is not valid JSON: {exc}"
                )

            latest_cursor = await conn.execute(
                """
                SELECT id, version_number, params_md5
                FROM param_versions
                WHERE param_set_id = ?
                ORDER BY version_number DESC
                LIMIT 1
                """,
                (param_set_id,),
            )
            latest_ver = await latest_cursor.fetchone()

            if latest_ver is None or latest_ver["params_md5"] != new_md5:
                next_version = (latest_ver["version_number"] + 1) if latest_ver else 1
                # parent_version_id: explicitly provided, or default to latest
                parent_id = body.parent_version_id
                if parent_id is None and latest_ver is not None:
                    parent_id = latest_ver["id"]
                pv_cursor = await conn.execute(
                    """
                    INSERT INTO param_versions (param_set_id, version_number, parent_version_id, params_md5, params_json, notes)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (param_set_id, next_version, parent_id, new_md5, body.params_json, body.notes),
                )
                param_version_id = pv_cursor.lastrowid
                new_version_id = param_version_id
                await conn.commit()
                await auto_queue_runs(conn, param_version_id)

        updated_cursor = await conn.execute(
            """
            SELECT ps.*, u.name AS owner_name, u.email AS owner_email
            FROM param_sets ps
            JOIN users u ON ps.owner_id = u.id
            WHERE ps.id = ?
            """,
            (param_set_id,),
        )
        updated = await updated_cursor.fetchone()

    result = _row_to_dict(updated)
    if new_version_id is not None:
        result["new_version_id"] = new_version_id
    return result


@router.delete("/{param_set_id}", status_code=204)
async def delete_param_set(param_set_id: int, request: Request):
    """Delete a param set. Auth required; owner only."""
    user = await require_user(request)

    async with get_async_db() as conn:
        cursor = await conn.execute(
            "SELECT owner_id FROM param_sets WHERE id = ?", (param_set_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Param set not found")
        if row["owner_id"] != user["id"]:
            raise HTTPException(status_code=403, detail="Not the owner")

        await conn.execute("DELETE FROM param_sets WHERE id = ?", (param_set_id,))
        await conn.commit()


class ForkBody(BaseModel):
    name: str | None = None


@router.post("/{param_set_id}/fork", status_code=201)
async def fork_param_set(param_set_id: int, request: Request, body: ForkBody = ForkBody()):
    """Fork a param set: copy latest version into a new ParamSet + ParamVersion + auto-queue runs. Auth required."""
    user = await require_user(request)

    async with get_async_db() as conn:
        source_cursor = await conn.execute(
            "SELECT * FROM param_sets WHERE id = ?", (param_set_id,)
        )
        source = await source_cursor.fetchone()
        if source is None:
            raise HTTPException(status_code=404, detail="Param set not found")

        # Get latest version's params
        ver_cursor = await conn.execute(
            """
            SELECT params_json, params_md5
            FROM param_versions
            WHERE param_set_id = ?
            ORDER BY version_number DESC
            LIMIT 1
            """,
            (param_set_id,),
        )
        latest_ver = await ver_cursor.fetchone()
        if latest_ver is None:
            raise HTTPException(status_code=404, detail="Source param set has no versions")

        fork_name = body.name or f"{source['name']} (fork)"

        ps_cursor = await conn.execute(
            """
            INSERT INTO param_sets (name, description, owner_id, forked_from_id)
            VALUES (?, ?, ?, ?)
            """,
            (fork_name, source["description"], user["id"], param_set_id),
        )
        new_param_set_id = ps_cursor.lastrowid

        pv_cursor = await conn.execute(
            """
            INSERT INTO param_versions (param_set_id, version_number, params_md5, params_json)
            VALUES (?, 1, ?, ?)
            """,
            (new_param_set_id, latest_ver["params_md5"], latest_ver["params_json"]),
        )
        param_version_id = pv_cursor.lastrowid
        await conn.commit()

        await auto_queue_runs(conn, param_version_id)

        row_cursor = await conn.execute(
            """
            SELECT ps.*, u.name AS owner_name, u.email AS owner_email
            FROM param_sets ps
            JOIN users u ON ps.owner_id = u.id
            WHERE ps.id = ?
            """,
            (new_param_set_id,),
        )
        row = await row_cursor.fetchone()

    return _row_to_dict(row)


@router.get("/{param_set_id}/versions")
async def list_versions(param_set_id: int):
    """List all versions for a param set."""
    async with get_async_db() as conn:
        ps_cursor = await conn.execute(
            "SELECT id FROM param_sets WHERE id = ?", (param_set_id,)
        )
        if await ps_cursor.fetchone() is None:
            raise HTTPException(status_code=404, detail="Param set not found")

        cursor = await conn.execute(
            """
            SELECT id, version_number, parent_version_id, params_md5, created_at
            FROM param_versions
            WHERE param_set_id = ?
            ORDER BY version_number DESC
            """,
            (param_set_id,),
        )
        rows = await cursor.fetchall()

    return [_row_to_dict(r) for r in rows]


@router.get("/{param_set_id}/versions/{version_id}")
async def get_version(param_set_id: int, version_id: int):
    """Get a specific version detail with its runs."""
    async with get_async_db() as conn:
        cursor = await conn.execute(
            """
            SELECT id, version_number, parent_version_id, params_md5, params_json, notes, created_at
            FROM param_versions
            WHERE id = ? AND param_set_id = ?
            """,
            (version_id, param_set_id),
        )
        row = await cursor.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Version not found")

        item = _row_to_dict(row)

        runs_cursor = await conn.execute(
            """
            SELECT id, test_type, status, total_eclipses, detected, created_at, completed_at
            FROM runs
            WHERE param_version_id = ?
            ORDER BY created_at DESC
            """,
            (version_id,),
        )
        runs_list = [_row_to_dict(r) for r in await runs_cursor.fetchall()]

        # Compute overall_pass for each done run
        for run in runs_list:
            if run["status"] == "done":
                op_cursor = await conn.execute(
                    """
                    SELECT SUM(CASE WHEN detected = 1 OR (moon_error_arcmin IS NOT NULL AND moon_error_arcmin < 60) THEN 1 ELSE 0 END) AS overall_pass
                    FROM eclipse_results WHERE run_id = ?
                    """,
                    (run["id"],),
                )
                op_row = await op_cursor.fetchone()
                run["overall_pass"] = op_row["overall_pass"] or 0
            else:
                run["overall_pass"] = None

        item["runs"] = runs_list

        # Walk ancestor chain
        ancestors = []
        current_parent_id = item.get("parent_version_id")
        seen = set()
        while current_parent_id and current_parent_id not in seen:
            seen.add(current_parent_id)
            anc_cursor = await conn.execute(
                """
                SELECT pv.id, pv.version_number, pv.parent_version_id, pv.params_md5, pv.params_json, pv.notes, pv.created_at
                FROM param_versions pv
                WHERE pv.id = ?
                """,
                (current_parent_id,),
            )
            anc_row = await anc_cursor.fetchone()
            if not anc_row:
                break
            anc = _row_to_dict(anc_row)

            # Get detection stats for this ancestor
            for test_type in ("solar", "lunar"):
                stat_cursor = await conn.execute(
                    """
                    SELECT detected, total_eclipses FROM runs
                    WHERE param_version_id = ? AND test_type = ? AND status = 'done'
                    ORDER BY completed_at DESC LIMIT 1
                    """,
                    (current_parent_id, test_type),
                )
                stat_row = await stat_cursor.fetchone()
                if stat_row:
                    anc[f"{test_type}_detected"] = stat_row["detected"]
                    anc[f"{test_type}_total"] = stat_row["total_eclipses"]
                else:
                    anc[f"{test_type}_detected"] = None
                    anc[f"{test_type}_total"] = None

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
        cursor = await conn.execute(
            """
            SELECT pv.id, ps.owner_id
            FROM param_versions pv
            JOIN param_sets ps ON pv.param_set_id = ps.id
            WHERE pv.id = ? AND pv.param_set_id = ?
            """,
            (version_id, param_set_id),
        )
        row = await cursor.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Version not found")
        if row["owner_id"] != user["id"]:
            raise HTTPException(status_code=403, detail="Not the owner")

        await conn.execute(
            "UPDATE param_versions SET notes = ? WHERE id = ?",
            (body.notes, version_id),
        )
        await conn.commit()

    return {"ok": True}
