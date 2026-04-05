"""Param set routes: CRUD + fork."""
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


@router.get("")
async def list_param_sets():
    """List all param sets with owner info and latest done runs."""
    async with get_async_db() as conn:
        cursor = await conn.execute(
            """
            SELECT p.*, u.name AS owner_name, u.email AS owner_email
            FROM param_sets p
            JOIN users u ON p.owner_id = u.id
            ORDER BY p.created_at DESC
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

            # Latest done runs (one per test_type)
            run_cursor = await conn.execute(
                """
                SELECT id, test_type, status, total_eclipses, detected, completed_at
                FROM runs
                WHERE param_set_id = ? AND status = 'done'
                ORDER BY completed_at DESC
                """,
                (item["id"],),
            )
            run_rows = await run_cursor.fetchall()
            item["latest_runs"] = [_row_to_dict(r) for r in run_rows]

            result.append(item)

    return result


class CreateParamSetBody(BaseModel):
    name: str
    description: str | None = None
    params_json: str


@router.post("", status_code=201)
async def create_param_set(body: CreateParamSetBody, request: Request):
    """Create a new param set. Auth required."""
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
        cursor = await conn.execute(
            """
            INSERT INTO param_sets (name, description, params_md5, params_json, owner_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (body.name.strip(), body.description, params_md5, body.params_json, user["id"]),
        )
        await conn.commit()
        row_cursor = await conn.execute(
            """
            SELECT p.*, u.name AS owner_name, u.email AS owner_email
            FROM param_sets p
            JOIN users u ON p.owner_id = u.id
            WHERE p.id = ?
            """,
            (cursor.lastrowid,),
        )
        row = await row_cursor.fetchone()

    return _row_to_dict(row)


@router.get("/{param_set_id}")
async def get_param_set(param_set_id: int):
    """Get a single param set with owner info."""
    async with get_async_db() as conn:
        cursor = await conn.execute(
            """
            SELECT p.*, u.name AS owner_name, u.email AS owner_email
            FROM param_sets p
            JOIN users u ON p.owner_id = u.id
            WHERE p.id = ?
            """,
            (param_set_id,),
        )
        row = await cursor.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Param set not found")

    return _row_to_dict(row)


class UpdateParamSetBody(BaseModel):
    name: str | None = None
    description: str | None = None
    params_json: str | None = None


@router.put("/{param_set_id}")
async def update_param_set(param_set_id: int, body: UpdateParamSetBody, request: Request):
    """Partial update. Auth required; owner only."""
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

        updates: dict = {}
        if body.name is not None:
            updates["name"] = body.name.strip()
        if body.description is not None:
            updates["description"] = body.description
        if body.params_json is not None:
            try:
                updates["params_md5"] = _compute_md5(body.params_json)
            except (json.JSONDecodeError, ValueError) as exc:
                raise HTTPException(
                    status_code=422, detail=f"params_json is not valid JSON: {exc}"
                )
            updates["params_json"] = body.params_json

        if updates:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values()) + [param_set_id]
            await conn.execute(
                f"UPDATE param_sets SET {set_clause} WHERE id = ?", values
            )
            await conn.commit()

        updated_cursor = await conn.execute(
            """
            SELECT p.*, u.name AS owner_name, u.email AS owner_email
            FROM param_sets p
            JOIN users u ON p.owner_id = u.id
            WHERE p.id = ?
            """,
            (param_set_id,),
        )
        updated = await updated_cursor.fetchone()

    return _row_to_dict(updated)


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
    """Fork a param set for the current user. Auth required."""
    user = await require_user(request)

    async with get_async_db() as conn:
        source_cursor = await conn.execute(
            "SELECT * FROM param_sets WHERE id = ?", (param_set_id,)
        )
        source = await source_cursor.fetchone()
        if source is None:
            raise HTTPException(status_code=404, detail="Param set not found")

        fork_name = body.name or f"{source['name']} (fork)"

        cursor = await conn.execute(
            """
            INSERT INTO param_sets
                (name, description, params_md5, params_json, owner_id, forked_from_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                fork_name,
                source["description"],
                source["params_md5"],
                source["params_json"],
                user["id"],
                param_set_id,
            ),
        )
        await conn.commit()

        row_cursor = await conn.execute(
            """
            SELECT p.*, u.name AS owner_name, u.email AS owner_email
            FROM param_sets p
            JOIN users u ON p.owner_id = u.id
            WHERE p.id = ?
            """,
            (cursor.lastrowid,),
        )
        row = await row_cursor.fetchone()

    return _row_to_dict(row)
