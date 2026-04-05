"""Auth routes: register, login, logout, me."""
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from server.auth import (
    SESSION_LIFETIME_DAYS,
    create_session,
    delete_session,
    hash_password,
    require_user,
    verify_password,
)
from server.db import get_async_db

router = APIRouter(prefix="/api/auth")

COOKIE_NAME = "tychos_session"
COOKIE_MAX_AGE = SESSION_LIFETIME_DAYS * 24 * 60 * 60  # seconds


def _set_session_cookie(response: Response, session_id: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=session_id,
        httponly=True,
        samesite="lax",
        max_age=COOKIE_MAX_AGE,
    )


class RegisterBody(BaseModel):
    email: str
    name: str
    password: str


class LoginBody(BaseModel):
    email: str
    password: str


@router.post("/register")
async def register(body: RegisterBody, response: Response):
    """Create a new user account, open a session, set cookie, return user."""
    async with get_async_db() as conn:
        cursor = await conn.execute(
            "SELECT id FROM users WHERE email = ?", (body.email,)
        )
        existing = await cursor.fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="Email already registered")
        password_hash = hash_password(body.password)
        cursor = await conn.execute(
            "INSERT INTO users (email, name, password_hash) VALUES (?, ?, ?)",
            (body.email, body.name, password_hash),
        )
        await conn.commit()
        user_id = cursor.lastrowid

    session_id = await create_session(user_id)
    _set_session_cookie(response, session_id)
    return {"id": user_id, "email": body.email, "name": body.name}


@router.post("/login")
async def login(body: LoginBody, response: Response):
    """Authenticate with email + password, open a session, set cookie, return user."""
    async with get_async_db() as conn:
        cursor = await conn.execute(
            "SELECT id, email, name, password_hash FROM users WHERE email = ?",
            (body.email,),
        )
        row = await cursor.fetchone()

    if row is None or not verify_password(body.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    session_id = await create_session(row["id"])
    _set_session_cookie(response, session_id)
    return {"id": row["id"], "email": row["email"], "name": row["name"]}


@router.post("/logout")
async def logout(request: Request, response: Response):
    """Delete the current session and clear the cookie."""
    session_id = request.cookies.get(COOKIE_NAME)
    if session_id:
        await delete_session(session_id)
    response.delete_cookie(key=COOKIE_NAME)
    return {"ok": True}


@router.get("/me")
async def me(user: dict = Depends(require_user)):
    """Return the currently authenticated user, or 401."""
    return user
