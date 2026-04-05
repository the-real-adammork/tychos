# Python Server + React SPA Rewrite Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Next.js with a FastAPI Python server + Vite React SPA while keeping all existing shadcn UI components.

**Architecture:** FastAPI serves the API and static React files. Eclipse computation lives in a scanner service (pure functions, no DB). A background worker thread processes queued runs and batch-writes results. React SPA uses react-router-dom instead of Next.js routing.

**Tech Stack:** FastAPI, uvicorn, bcrypt, SQLite (raw sqlite3), Vite, React 19, react-router-dom, shadcn/ui, Tailwind CSS 4

---

## File Map

### New files

```
server/
  app.py                    # FastAPI app, CORS, static file serving
  auth.py                   # password hashing, session cookie helpers
  db.py                     # SQLite connection, schema init, query helpers
  worker.py                 # background thread for queued runs
  services/
    scanner.py              # pure computation: eclipse scanning
  api/
    auth_routes.py
    params_routes.py
    runs_routes.py
    results_routes.py
    compare_routes.py

tests/
  test_scanner.py           # tests for scanner.py (new)
```

### Modified files

```
admin/                      # convert from Next.js to Vite SPA
  package.json              # replace next with vite + react-router-dom
  vite.config.ts            # new (replaces next.config.ts)
  index.html                # new (Vite entry)
  src/
    main.tsx                # new (replaces app/layout.tsx)
    App.tsx                 # new (router + sidebar + auth context)
    pages/                  # moved from app/*, stripped Next.js imports
    components/sidebar.tsx  # swap next/link → react-router-dom Link

tests/
  helpers.py                # unchanged
  test_smoke.py             # unchanged
```

### Deleted files

```
admin/src/app/              # entire Next.js app directory
admin/src/generated/        # Prisma generated client
admin/src/lib/              # Node auth, db, worker
admin/src/instrumentation.ts
admin/prisma/
admin/next.config.ts
admin/next-env.d.ts
tests/db.py                 # replaced by server/db.py
tests/run_eclipses.py       # replaced by server/services/scanner.py
```

---

## Task 1: FastAPI app skeleton + database layer

**Files:**
- Create: `server/app.py`
- Create: `server/db.py`
- Create: `server/requirements.txt`

- [ ] **Step 1: Create server/requirements.txt**

```
fastapi
uvicorn[standard]
bcrypt
```

- [ ] **Step 2: Install into existing venv**

```bash
source tychos_skyfield/.venv/bin/activate
pip install fastapi uvicorn[standard] bcrypt
```

- [ ] **Step 3: Create server/db.py**

```python
"""SQLite database connection and schema management."""
import sqlite3
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path(__file__).parent.parent / "results" / "tychos_results.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS "User" (
    "id" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    "email" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "passwordHash" TEXT NOT NULL,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS "User_email_key" ON "User"("email");

CREATE TABLE IF NOT EXISTS "Session" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "userId" INTEGER NOT NULL,
    "expiresAt" DATETIME NOT NULL,
    CONSTRAINT "Session_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User" ("id") ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS "ParamSet" (
    "id" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    "name" TEXT NOT NULL,
    "description" TEXT,
    "paramsMd5" TEXT NOT NULL,
    "paramsJson" TEXT NOT NULL,
    "ownerId" INTEGER NOT NULL,
    "forkedFromId" INTEGER,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "ParamSet_ownerId_fkey" FOREIGN KEY ("ownerId") REFERENCES "User" ("id") ON DELETE CASCADE,
    CONSTRAINT "ParamSet_forkedFromId_fkey" FOREIGN KEY ("forkedFromId") REFERENCES "ParamSet" ("id") ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS "Run" (
    "id" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    "paramSetId" INTEGER NOT NULL,
    "testType" TEXT NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'queued',
    "codeVersion" TEXT NOT NULL DEFAULT '1.0',
    "tsnCommit" TEXT,
    "skyfieldCommit" TEXT,
    "totalEclipses" INTEGER,
    "detected" INTEGER,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "startedAt" DATETIME,
    "completedAt" DATETIME,
    "error" TEXT,
    CONSTRAINT "Run_paramSetId_fkey" FOREIGN KEY ("paramSetId") REFERENCES "ParamSet" ("id") ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS "EclipseResult" (
    "id" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    "runId" INTEGER NOT NULL,
    "julianDayTt" REAL NOT NULL,
    "date" TEXT NOT NULL,
    "catalogType" TEXT NOT NULL,
    "magnitude" REAL NOT NULL,
    "detected" BOOLEAN NOT NULL,
    "thresholdArcmin" REAL NOT NULL,
    "minSeparationArcmin" REAL,
    "timingOffsetMin" REAL,
    "bestJd" REAL,
    "sunRaRad" REAL,
    "sunDecRad" REAL,
    "moonRaRad" REAL,
    "moonDecRad" REAL,
    CONSTRAINT "EclipseResult_runId_fkey" FOREIGN KEY ("runId") REFERENCES "Run" ("id") ON DELETE CASCADE
);
"""


def init_db():
    """Create tables if they don't exist."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript(SCHEMA)
    conn.close()


@contextmanager
def get_db():
    """Yield a sqlite3 connection with row_factory set to Row."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()
```

- [ ] **Step 4: Create server/app.py**

```python
"""FastAPI application."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from server.db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In production, serve the built React SPA
dist_path = Path(__file__).parent.parent / "admin" / "dist"
if dist_path.exists():
    app.mount("/", StaticFiles(directory=str(dist_path), html=True), name="spa")
```

- [ ] **Step 5: Verify server starts**

```bash
source tychos_skyfield/.venv/bin/activate
PYTHONPATH=. uvicorn server.app:app --reload --port 8000
```

Should start without errors. Ctrl+C to stop.

- [ ] **Step 6: Commit**

```bash
git add server/app.py server/db.py server/requirements.txt
git commit -m "feat(server): add FastAPI app skeleton and database layer"
```

---

## Task 2: Auth routes

**Files:**
- Create: `server/auth.py`
- Create: `server/api/auth_routes.py`

- [ ] **Step 1: Create server/auth.py**

```python
"""Authentication helpers: password hashing and session management."""
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt

from server.db import get_db

SESSION_DURATION = timedelta(days=30)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_session(user_id: int) -> str:
    session_id = str(uuid.uuid4())
    expires_at = datetime.now(timezone.utc) + SESSION_DURATION
    with get_db() as conn:
        conn.execute(
            'INSERT INTO "Session" ("id", "userId", "expiresAt") VALUES (?, ?, ?)',
            (session_id, user_id, expires_at.isoformat()),
        )
        conn.commit()
    return session_id


def get_session_user(session_id: str) -> dict | None:
    if not session_id:
        return None
    with get_db() as conn:
        row = conn.execute(
            'SELECT s."userId", s."expiresAt", u."id", u."email", u."name" '
            'FROM "Session" s JOIN "User" u ON s."userId" = u."id" '
            'WHERE s."id" = ?',
            (session_id,),
        ).fetchone()
    if not row:
        return None
    if datetime.fromisoformat(row["expiresAt"]) < datetime.now(timezone.utc):
        delete_session(session_id)
        return None
    return {"id": row["id"], "email": row["email"], "name": row["name"]}


def delete_session(session_id: str):
    with get_db() as conn:
        conn.execute('DELETE FROM "Session" WHERE "id" = ?', (session_id,))
        conn.commit()
```

- [ ] **Step 2: Create server/api/__init__.py**

Empty file.

```bash
mkdir -p server/api
touch server/api/__init__.py
touch server/__init__.py
touch server/services/__init__.py
```

- [ ] **Step 3: Create server/api/auth_routes.py**

```python
"""Auth API routes: register, login, logout."""
from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from server.auth import hash_password, verify_password, create_session, get_session_user, delete_session
from server.db import get_db

router = APIRouter(prefix="/api/auth")

COOKIE_NAME = "tychos_session"
COOKIE_MAX_AGE = 30 * 24 * 60 * 60  # 30 days


class RegisterBody(BaseModel):
    email: str
    name: str
    password: str


class LoginBody(BaseModel):
    email: str
    password: str


@router.post("/register")
def register(body: RegisterBody, response: Response):
    with get_db() as conn:
        existing = conn.execute('SELECT "id" FROM "User" WHERE "email" = ?', (body.email,)).fetchone()
        if existing:
            return Response(status_code=409, content='{"error":"Email already registered"}', media_type="application/json")
        hashed = hash_password(body.password)
        cur = conn.execute(
            'INSERT INTO "User" ("email", "name", "passwordHash") VALUES (?, ?, ?)',
            (body.email, body.name, hashed),
        )
        conn.commit()
        user_id = cur.lastrowid

    session_id = create_session(user_id)
    response.set_cookie(COOKIE_NAME, session_id, httponly=True, samesite="lax", max_age=COOKIE_MAX_AGE)
    return {"id": user_id, "email": body.email, "name": body.name}


@router.post("/login")
def login(body: LoginBody, response: Response):
    with get_db() as conn:
        row = conn.execute(
            'SELECT "id", "email", "name", "passwordHash" FROM "User" WHERE "email" = ?',
            (body.email,),
        ).fetchone()
    if not row or not verify_password(body.password, row["passwordHash"]):
        return Response(status_code=401, content='{"error":"Invalid email or password"}', media_type="application/json")

    session_id = create_session(row["id"])
    response.set_cookie(COOKIE_NAME, session_id, httponly=True, samesite="lax", max_age=COOKIE_MAX_AGE)
    return {"id": row["id"], "email": row["email"], "name": row["name"]}


@router.post("/logout")
def logout(request: Request, response: Response):
    session_id = request.cookies.get(COOKIE_NAME)
    if session_id:
        delete_session(session_id)
    response.delete_cookie(COOKIE_NAME)
    return {"ok": True}
```

- [ ] **Step 4: Register auth routes in app.py**

Add to `server/app.py` after CORS middleware:

```python
from server.api.auth_routes import router as auth_router
app.include_router(auth_router)
```

- [ ] **Step 5: Test auth**

```bash
PYTHONPATH=. uvicorn server.app:app --reload --port 8000 &
sleep 2
curl -X POST http://localhost:8000/api/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"test@test.com","name":"Test","password":"test123"}'
kill %1
```

Should return user JSON with Set-Cookie header.

- [ ] **Step 6: Commit**

```bash
git add server/
git commit -m "feat(server): add auth routes with session cookies"
```

---

## Task 3: Scanner service (pure computation)

**Files:**
- Create: `server/services/scanner.py`
- Create: `tests/test_scanner.py`

- [ ] **Step 1: Create server/services/scanner.py**

```python
"""Eclipse scanning — pure computation, no database, no side effects.

Takes parameters and eclipse catalog data, returns results as dicts.
"""
import json
import sys
from pathlib import Path

import numpy as np

# Add tychos_skyfield to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "tychos_skyfield"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "tests"))

from tychos_skyfield import baselib as T
from helpers import (
    scan_min_separation, scan_lunar_eclipse, lunar_threshold,
    SOLAR_DETECTION_THRESHOLD, MINUTE_IN_DAYS,
)

DATA_DIR = Path(__file__).parent.parent.parent / "tests" / "data"


def load_eclipse_catalog(test_type: str) -> list[dict]:
    path = DATA_DIR / f"{test_type}_eclipses.json"
    with open(path) as f:
        return json.load(f)


def scan_solar_eclipses(params: dict, eclipses: list[dict]) -> list[dict]:
    """Scan for solar eclipses. Pure computation — returns list of result dicts."""
    system = T.TychosSystem(params=params)
    threshold_arcmin = np.degrees(SOLAR_DETECTION_THRESHOLD) * 60
    results = []

    for ecl in eclipses:
        jd = ecl["julian_day_tt"]
        min_sep, best_jd, s_ra, s_dec, m_ra, m_dec = scan_min_separation(system, jd)
        det = min_sep < SOLAR_DETECTION_THRESHOLD

        results.append({
            "julianDayTt": jd,
            "date": ecl["date"],
            "catalogType": ecl["type"],
            "magnitude": ecl["magnitude"],
            "detected": bool(det),
            "thresholdArcmin": round(threshold_arcmin, 4),
            "minSeparationArcmin": round(np.degrees(min_sep) * 60, 2),
            "timingOffsetMin": round((best_jd - jd) / MINUTE_IN_DAYS, 1),
            "bestJd": float(best_jd),
            "sunRaRad": float(s_ra),
            "sunDecRad": float(s_dec),
            "moonRaRad": float(m_ra),
            "moonDecRad": float(m_dec),
        })

    return results


def scan_lunar_eclipses(params: dict, eclipses: list[dict]) -> list[dict]:
    """Scan for lunar eclipses. Pure computation — returns list of result dicts."""
    system = T.TychosSystem(params=params)
    results = []

    for ecl in eclipses:
        jd = ecl["julian_day_tt"]
        min_sep, best_jd, s_ra, s_dec, m_ra, m_dec = scan_lunar_eclipse(system, jd)
        threshold = lunar_threshold(ecl["type"])
        threshold_arcmin = np.degrees(threshold) * 60
        det = min_sep < threshold

        results.append({
            "julianDayTt": jd,
            "date": ecl["date"],
            "catalogType": ecl["type"],
            "magnitude": ecl["magnitude"],
            "detected": bool(det),
            "thresholdArcmin": round(threshold_arcmin, 4),
            "minSeparationArcmin": round(np.degrees(min_sep) * 60, 2),
            "timingOffsetMin": round((best_jd - jd) / MINUTE_IN_DAYS, 1),
            "bestJd": float(best_jd),
            "sunRaRad": float(s_ra),
            "sunDecRad": float(s_dec),
            "moonRaRad": float(m_ra),
            "moonDecRad": float(m_dec),
        })

    return results
```

- [ ] **Step 2: Create tests/test_scanner.py**

```python
"""Tests for the scanner service — pure computation, no database."""
import json
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "tychos_skyfield"))
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from server.services.scanner import scan_solar_eclipses, scan_lunar_eclipses


PARAMS_PATH = Path(__file__).parent.parent / "params" / "v1-original.json"


@pytest.fixture
def params():
    with open(PARAMS_PATH) as f:
        return json.load(f)


class TestSolarScanner:
    def test_detects_2017_total_solar_eclipse(self, params):
        eclipses = [{"julian_day_tt": 2457987.268519, "date": "2017-08-21T18:26:40", "type": "total", "magnitude": 1.0306}]
        results = scan_solar_eclipses(params, eclipses)
        assert len(results) == 1
        assert results[0]["detected"] is True
        assert results[0]["minSeparationArcmin"] < 48.0

    def test_returns_all_fields(self, params):
        eclipses = [{"julian_day_tt": 2457987.268519, "date": "2017-08-21T18:26:40", "type": "total", "magnitude": 1.0306}]
        results = scan_solar_eclipses(params, eclipses)
        r = results[0]
        required = ["julianDayTt", "date", "catalogType", "magnitude", "detected",
                     "thresholdArcmin", "minSeparationArcmin", "timingOffsetMin",
                     "bestJd", "sunRaRad", "sunDecRad", "moonRaRad", "moonDecRad"]
        for key in required:
            assert key in r, f"Missing key: {key}"

    def test_empty_input(self, params):
        results = scan_solar_eclipses(params, [])
        assert results == []


class TestLunarScanner:
    def test_detects_known_lunar_eclipse(self, params):
        eclipses = [{"julian_day_tt": 2458119.535625, "date": "2018-01-31T00:51:18", "type": "total", "magnitude": 2.294}]
        results = scan_lunar_eclipses(params, eclipses)
        assert len(results) == 1
        assert results[0]["detected"] is True

    def test_empty_input(self, params):
        results = scan_lunar_eclipses(params, [])
        assert results == []
```

- [ ] **Step 3: Run scanner tests**

```bash
source tychos_skyfield/.venv/bin/activate
PYTHONPATH=tychos_skyfield:tests:. pytest tests/test_scanner.py -v
```

All should pass.

- [ ] **Step 4: Commit**

```bash
git add server/services/scanner.py tests/test_scanner.py
git commit -m "feat(server): add scanner service with tests"
```

---

## Task 4: Worker (background thread)

**Files:**
- Create: `server/worker.py`

- [ ] **Step 1: Create server/worker.py**

```python
"""Background worker thread that processes queued eclipse runs."""
import json
import threading
import time
import traceback
from datetime import datetime, timezone

from server.db import get_db
from server.services.scanner import (
    scan_solar_eclipses, scan_lunar_eclipses, load_eclipse_catalog,
)

POLL_INTERVAL = 5  # seconds


def _process_one():
    """Pick up one queued run, execute it, write results."""
    with get_db() as conn:
        run = conn.execute(
            'SELECT r."id", r."testType", p."paramsJson" '
            'FROM "Run" r JOIN "ParamSet" p ON r."paramSetId" = p."id" '
            'WHERE r."status" = ? ORDER BY r."createdAt" ASC LIMIT 1',
            ("queued",),
        ).fetchone()

    if not run:
        return

    run_id = run["id"]
    test_type = run["testType"]
    params = json.loads(run["paramsJson"])

    # Mark running
    with get_db() as conn:
        conn.execute(
            'UPDATE "Run" SET "status" = ?, "startedAt" = ? WHERE "id" = ?',
            ("running", datetime.now(timezone.utc).isoformat(), run_id),
        )
        conn.commit()

    try:
        eclipses = load_eclipse_catalog(test_type)

        if test_type == "solar":
            results = scan_solar_eclipses(params, eclipses)
        else:
            results = scan_lunar_eclipses(params, eclipses)

        detected = sum(1 for r in results if r["detected"])

        # Batch write all results in one transaction
        with get_db() as conn:
            conn.executemany(
                'INSERT INTO "EclipseResult" '
                '("runId", "julianDayTt", "date", "catalogType", "magnitude", '
                '"detected", "thresholdArcmin", "minSeparationArcmin", "timingOffsetMin", '
                '"bestJd", "sunRaRad", "sunDecRad", "moonRaRad", "moonDecRad") '
                'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                [(run_id, r["julianDayTt"], r["date"], r["catalogType"], r["magnitude"],
                  r["detected"], r["thresholdArcmin"], r["minSeparationArcmin"],
                  r["timingOffsetMin"], r["bestJd"], r["sunRaRad"], r["sunDecRad"],
                  r["moonRaRad"], r["moonDecRad"]) for r in results],
            )
            conn.execute(
                'UPDATE "Run" SET "status" = ?, "completedAt" = ?, "totalEclipses" = ?, "detected" = ? WHERE "id" = ?',
                ("done", datetime.now(timezone.utc).isoformat(), len(results), detected, run_id),
            )
            conn.commit()

        print(f"[worker] Run {run_id} complete: {detected}/{len(results)} detected")

    except Exception:
        error = traceback.format_exc()[:2000]
        with get_db() as conn:
            conn.execute(
                'UPDATE "Run" SET "status" = ?, "completedAt" = ?, "error" = ? WHERE "id" = ?',
                ("failed", datetime.now(timezone.utc).isoformat(), error, run_id),
            )
            conn.commit()
        print(f"[worker] Run {run_id} failed: {error}")


def _worker_loop():
    while True:
        try:
            _process_one()
        except Exception as e:
            print(f"[worker] poll error: {e}")
        time.sleep(POLL_INTERVAL)


def start_worker():
    """Start the background worker in a daemon thread."""
    thread = threading.Thread(target=_worker_loop, daemon=True)
    thread.start()
    print("[worker] Background worker started")
```

- [ ] **Step 2: Start worker from app.py lifespan**

Update `server/app.py` lifespan:

```python
from server.worker import start_worker

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    start_worker()
    yield
```

- [ ] **Step 3: Commit**

```bash
git add server/worker.py server/app.py
git commit -m "feat(server): add background worker thread for queued runs"
```

---

## Task 5: Params, Runs, Results, Compare API routes

**Files:**
- Create: `server/api/params_routes.py`
- Create: `server/api/runs_routes.py`
- Create: `server/api/results_routes.py`
- Create: `server/api/compare_routes.py`

These are direct ports of the Next.js API routes to FastAPI. Each route uses `server.db.get_db()` for database access and `server.auth.get_session_user()` for auth. The auth check reads the session cookie from the request.

A helper dependency to extract the current user:

```python
# Add to server/auth.py
from fastapi import Request, HTTPException

def require_user(request: Request) -> dict:
    session_id = request.cookies.get("tychos_session")
    user = get_session_user(session_id)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return user
```

- [ ] **Step 1: Add require_user to server/auth.py**

Append the `require_user` function shown above.

- [ ] **Step 2: Create server/api/params_routes.py**

Port the params CRUD + fork routes. GET list, POST create, GET single, PUT update (owner only), DELETE (owner only), POST fork. Use `hashlib.md5` for paramsMd5 computation with `json.dumps(sort_keys=True)` canonicalization.

- [ ] **Step 3: Create server/api/runs_routes.py**

Port runs list (GET with optional filters), create (POST, sets status "queued"), get single (GET by id).

- [ ] **Step 4: Create server/api/results_routes.py**

Port paginated results for a run. GET with page, catalogType, detected filters. Page size 50.

- [ ] **Step 5: Create server/api/compare_routes.py**

Port comparison endpoint. GET with a, b param set IDs and type. Find latest done run for each, get all results, compute changed eclipses.

- [ ] **Step 6: Register all routers in app.py**

```python
from server.api.params_routes import router as params_router
from server.api.runs_routes import router as runs_router
from server.api.results_routes import router as results_router
from server.api.compare_routes import router as compare_router

app.include_router(auth_router)
app.include_router(params_router)
app.include_router(runs_router)
app.include_router(results_router)
app.include_router(compare_router)
```

- [ ] **Step 7: Test all routes with curl**

```bash
PYTHONPATH=. uvicorn server.app:app --reload --port 8000
# Test params CRUD, runs, etc.
```

- [ ] **Step 8: Commit**

```bash
git add server/api/ server/auth.py server/app.py
git commit -m "feat(server): add params, runs, results, compare API routes"
```

---

## Task 6: Convert admin/ from Next.js to Vite SPA

**Files:**
- Create: `admin/vite.config.ts`
- Create: `admin/index.html`
- Create: `admin/src/main.tsx`
- Create: `admin/src/App.tsx`
- Modify: `admin/package.json`
- Move: `admin/src/app/*.tsx` → `admin/src/pages/*.tsx`
- Modify: `admin/src/components/sidebar.tsx` — swap Next.js imports
- Delete: `admin/src/app/`, `admin/src/generated/`, `admin/src/lib/`, `admin/src/instrumentation.ts`, `admin/prisma/`, `admin/next.config.ts`

- [ ] **Step 1: Update package.json**

Replace Next.js deps with Vite + react-router-dom. Keep react, shadcn, tailwind, lucide-react, date-fns.

```bash
cd admin
npm uninstall next @prisma/client prisma @types/bcryptjs bcryptjs
npm install react-router-dom
npm install -D vite @vitejs/plugin-react
```

Update scripts in package.json:
```json
"scripts": {
  "dev": "vite",
  "build": "vite build",
  "preview": "vite preview"
}
```

- [ ] **Step 2: Create admin/vite.config.ts**

```typescript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
```

- [ ] **Step 3: Create admin/index.html**

```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Tychos Admin</title>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet" />
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 4: Create admin/src/main.tsx**

```typescript
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./globals.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>
);
```

- [ ] **Step 5: Create admin/src/App.tsx**

```typescript
import { Routes, Route, Navigate } from "react-router-dom";
import { useState, useEffect, createContext, useContext } from "react";
import { Sidebar } from "@/components/sidebar";

// Pages (will be moved in next steps)
import DashboardPage from "@/pages/DashboardPage";
import LoginPage from "@/pages/LoginPage";
import RegisterPage from "@/pages/RegisterPage";
import ParametersPage from "@/pages/ParametersPage";
import ParamDetailPage from "@/pages/ParamDetailPage";
import RunsPage from "@/pages/RunsPage";
import ResultsPage from "@/pages/ResultsPage";
import ComparePage from "@/pages/ComparePage";

type User = { id: number; email: string; name: string } | null;

const AuthContext = createContext<{
  user: User;
  setUser: (u: User) => void;
}>({ user: null, setUser: () => {} });

export function useAuth() {
  return useContext(AuthContext);
}

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" />;
  return <>{children}</>;
}

export default function App() {
  const [user, setUser] = useState<User>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/auth/me")
      .then((r) => (r.ok ? r.json() : null))
      .then((u) => setUser(u))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return null;

  return (
    <AuthContext.Provider value={{ user, setUser }}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route
          path="/*"
          element={
            <ProtectedRoute>
              <div className="flex h-screen overflow-hidden">
                <Sidebar userName={user!.name} userEmail={user!.email} />
                <main className="flex-1 overflow-y-auto p-6">
                  <Routes>
                    <Route path="/" element={<DashboardPage />} />
                    <Route path="/parameters" element={<ParametersPage />} />
                    <Route path="/parameters/:id" element={<ParamDetailPage />} />
                    <Route path="/runs" element={<RunsPage />} />
                    <Route path="/results/:runId" element={<ResultsPage />} />
                    <Route path="/compare" element={<ComparePage />} />
                  </Routes>
                </main>
              </div>
            </ProtectedRoute>
          }
        />
      </Routes>
    </AuthContext.Provider>
  );
}
```

Note: This requires a `/api/auth/me` endpoint. Add to `server/api/auth_routes.py`:

```python
@router.get("/me")
def me(request: Request):
    session_id = request.cookies.get(COOKIE_NAME)
    user = get_session_user(session_id)
    if not user:
        return Response(status_code=401)
    return user
```

- [ ] **Step 6: Update sidebar.tsx**

Replace `next/link` with `react-router-dom` `Link`, `usePathname` with `useLocation`, `useRouter` with `useNavigate`:

```typescript
// Replace imports:
import { Link, useLocation, useNavigate } from "react-router-dom";

// Replace inside component:
const { pathname } = useLocation();
const navigate = useNavigate();

async function handleSignOut() {
  await fetch("/api/auth/logout", { method: "POST" });
  navigate("/login");
}
```

- [ ] **Step 7: Move and convert page components**

Create `admin/src/pages/` and move each page. Strip Next.js-specific code (server components become client components, `redirect()` becomes `<Navigate>`, `useRouter` becomes `useNavigate`, dynamic params from `useParams()`).

Key conversions:
- Dashboard: was server component fetching Prisma → now client component fetching `/api/` endpoints
- ParamDetail: `params: Promise<{id}>` → `useParams()` from react-router-dom
- Results: same `useParams()` change

- [ ] **Step 8: Delete Next.js files**

```bash
rm -rf admin/src/app admin/src/generated admin/src/lib admin/src/instrumentation.ts
rm -rf admin/prisma admin/next.config.ts admin/next-env.d.ts admin/.next
```

- [ ] **Step 9: Add dashboard API endpoint**

The dashboard page was a server component that queried Prisma directly. Now it needs an API endpoint. Add to `server/api/`:

Create `server/api/dashboard_routes.py` with a GET `/api/dashboard` that returns stats, recent runs, and leaderboard data.

- [ ] **Step 10: Verify SPA builds and runs**

```bash
cd admin && npm run dev
```

Visit http://localhost:5173 — should proxy API calls to FastAPI on 8000.

- [ ] **Step 11: Commit**

```bash
git add admin/ server/api/auth_routes.py server/api/dashboard_routes.py
git commit -m "feat(admin): convert from Next.js to Vite SPA with react-router-dom"
```

---

## Task 7: Clean up old files and verify end-to-end

**Files:**
- Delete: `tests/db.py`
- Delete: `tests/run_eclipses.py`
- Delete: `admin/src/lib/` (if any remnants)

- [ ] **Step 1: Delete obsolete files**

```bash
rm tests/db.py tests/run_eclipses.py
```

- [ ] **Step 2: Verify all tests pass**

```bash
source tychos_skyfield/.venv/bin/activate
PYTHONPATH=tychos_skyfield:tests:. pytest tests/ -v
```

Smoke tests and scanner tests should all pass.

- [ ] **Step 3: End-to-end verification**

1. Start server: `PYTHONPATH=. uvicorn server.app:app --reload --port 8000`
2. Start SPA: `cd admin && npm run dev`
3. Open http://localhost:5173
4. Register / login
5. View dashboard
6. Go to Parameters, see v1-original
7. Queue a solar run
8. Watch it complete on Runs page
9. View results
10. Fork a param set, modify a value, queue a run, compare

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore: remove obsolete Next.js and Python db files"
```
