"""Auth helpers: password hashing, session management, and FastAPI dependency."""
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import HTTPException, Request

from server.db import get_async_db

SESSION_LIFETIME_DAYS = 30


def hash_password(password: str) -> str:
    """Return a bcrypt hash of the given password."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    """Return True if password matches the bcrypt hash."""
    return bcrypt.checkpw(password.encode(), hashed.encode())


async def create_session(user_id: int) -> str:
    """Insert a new session row and return its id (uuid4)."""
    session_id = str(uuid.uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(days=SESSION_LIFETIME_DAYS)
    async with get_async_db() as conn:
        await conn.execute(
            "INSERT INTO sessions (id, user_id, expires_at) VALUES (?, ?, ?)",
            (session_id, user_id, expires_at.isoformat()),
        )
        await conn.commit()
    return session_id


async def get_session_user(session_id: str) -> dict | None:
    """Look up a session and join with users.

    Deletes expired sessions and returns None if missing or expired.
    Returns {"id", "email", "name"} on success.
    """
    async with get_async_db() as conn:
        now = datetime.now(timezone.utc).isoformat()
        # Purge any expired sessions for this id
        await conn.execute(
            "DELETE FROM sessions WHERE id = ? AND expires_at <= ?",
            (session_id, now),
        )
        await conn.commit()
        cursor = await conn.execute(
            """
            SELECT u.id, u.email, u.name
            FROM sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.id = ?
            """,
            (session_id,),
        )
        row = await cursor.fetchone()
    if row is None:
        return None
    return {"id": row["id"], "email": row["email"], "name": row["name"]}


async def delete_session(session_id: str) -> None:
    """Delete a session from the database."""
    async with get_async_db() as conn:
        await conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        await conn.commit()


async def require_user(request: Request) -> dict:
    """FastAPI dependency — reads the tychos_session cookie and returns the user dict.

    Raises HTTPException(401) if the session is absent or expired.
    """
    session_id = request.cookies.get("tychos_session")
    if not session_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = await get_session_user(session_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Session expired or invalid")
    return user
