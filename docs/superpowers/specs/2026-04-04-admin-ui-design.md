# Tychos Admin UI — Design Spec

## Overview

A self-hosted web application for viewing, comparing, and collaborating on Tychos model eclipse prediction results. Multiple users can create parameter versions, queue test runs, and compare detection accuracy.

Built as a single Next.js 16 app following the gowild architecture pattern: Prisma ORM + SQLite + shadcn/ui + Tailwind CSS.

## Architecture

### Stack

- **Framework**: Next.js 16 (App Router, server + client components)
- **Database**: SQLite via Prisma ORM (single file, single source of truth)
- **UI**: shadcn/ui components + Tailwind CSS 4
- **Auth**: Email/password with session tokens in httpOnly cookies
- **Background Jobs**: Node worker polling a jobs table, spawning Python subprocess
- **Test Runner**: Existing Python `run_eclipses.py` invoked as subprocess

### Data Flow

```
Browser (shadcn UI)
    ↓ fetch()
Next.js API Routes (/api/auth, /api/params, /api/runs, /api/results)
    ↓ Prisma ORM
SQLite Database (users, param_sets, runs, eclipse_results, sessions)
    ↑ also written by
Background Worker → Python subprocess (run_eclipses.py)
```

The Next.js app and Python runner share the same SQLite database. Prisma owns the schema. The Python runner reads `paramsJson` from the `ParamSet` table and writes `EclipseResult` rows directly.

## Prisma Schema

### User

```
id            Int       @id @default(autoincrement())
email         String    @unique
name          String
passwordHash  String
createdAt     DateTime  @default(now())
paramSets     ParamSet[]
sessions      Session[]
```

### Session

```
id        String   @id @default(uuid())
userId    Int      → User
expiresAt DateTime
```

Simple token auth. Token stored in httpOnly cookie. No JWT.

### ParamSet

```
id           Int       @id @default(autoincrement())
name         String
description  String?
paramsMd5    String
paramsJson   String    (full JSON blob — db is self-contained)
ownerId      Int       → User
forkedFromId Int?      → ParamSet (self-relation, null = created from scratch)
createdAt    DateTime  @default(now())
runs         Run[]
```

Users can fork any other user's param set. The `forkedFromId` tracks lineage.

### Run

```
id              Int       @id @default(autoincrement())
paramSetId      Int       → ParamSet
testType        String    ("solar" | "lunar")
status          String    ("queued" | "running" | "done" | "failed")
codeVersion     String
tsnCommit       String?
skyfieldCommit  String?
totalEclipses   Int?
detected        Int?
createdAt       DateTime  @default(now())
startedAt       DateTime?
completedAt     DateTime?
error           String?
results         EclipseResult[]
```

### EclipseResult

```
id                    Int     @id @default(autoincrement())
runId                 Int     → Run
julianDayTt           Float
date                  String
catalogType           String
magnitude             Float
detected              Boolean
thresholdArcmin       Float
minSeparationArcmin   Float?
timingOffsetMin       Float?
bestJd                Float?
sunRaRad              Float?
sunDecRad             Float?
moonRaRad             Float?
moonDecRad            Float?
```

## Pages

### 1. Dashboard (/)

Server component. Stats cards showing:
- Total parameter versions
- Best solar detection rate (which version)
- Best lunar detection rate (which version)
- Recent runs list (version, type, result, status)
- Leaderboard — param versions ranked by average detection rate, showing owner

### 2. Parameters (/parameters)

List all param versions from all users. Each row shows: name, owner, creation date, forked-from (if any), latest run results. Actions:
- **Create new** — blank or from JSON upload
- **Fork** — copy another user's version to edit
- **Edit** — click into a version to modify the 34 body parameters
- **Queue run** — trigger solar/lunar test from this page

Detail view (`/parameters/[id]`) shows the full parameter editor — table of all bodies with their 8 orbital parameters, editable inline.

### 3. Runs (/runs)

Table of all test executions across all users. Columns: param version, owner, test type, status, detection rate, timing, date. Filterable by user, param version, status.

Queued/running jobs show progress. Clicking a completed run navigates to Results.

### 4. Results (/results/[runId])

Per-eclipse detail table for a specific run. Columns: date, type, magnitude, detected (yes/no), min separation, timing offset. Filterable by eclipse type, detected/missed, date range.

Expandable rows show Sun/Moon RA/Dec positions at predicted minimum.

### 5. Compare (/compare)

Two dropdown selectors to pick any two param versions. Shows:
- **Detection rate comparison** — side-by-side with delta (e.g., +15 newly detected)
- **Changed eclipses table** — eclipses that flipped status between versions, showing both separations
- **Parameter diff** — git-style diff of changed values, grouped by body

## Background Worker

A Node.js worker running inside the same process (via `instrumentation.ts` startup hook, same pattern as gowild's scheduler):

1. Polls the `Run` table every 10 seconds for rows with `status = "queued"`
2. Picks the oldest queued run, sets status to `"running"`
3. Reads `paramsJson` from the associated `ParamSet`
4. Writes params to a temp JSON file
5. Spawns: `python tests/run_eclipses.py <temp_params_file> --db <db_path> --run-id <id>`
6. On success: sets status to `"done"`, populates `totalEclipses`, `detected`, `completedAt`
7. On failure: sets status to `"failed"`, stores error message
8. Only one run executes at a time (sequential queue)

The Python runner needs a small modification to accept `--db` and `--run-id` flags so it writes to the Prisma-managed database and associates results with the correct run.

## Auth Flow

1. **Register**: POST /api/auth/register — email, name, password. Hash password with bcrypt. Create user + session. Set cookie.
2. **Login**: POST /api/auth/login — email, password. Verify hash. Create session. Set cookie.
3. **Logout**: POST /api/auth/logout — delete session row, clear cookie.
4. **Session check**: Middleware reads cookie, looks up session, attaches user to request. Expired sessions rejected.

No email verification for simplicity. Can add later.

## API Routes

```
POST   /api/auth/register
POST   /api/auth/login
POST   /api/auth/logout

GET    /api/params              — list all param sets (with owner info)
POST   /api/params              — create new param set
GET    /api/params/[id]         — get single param set with full JSON
PUT    /api/params/[id]         — update (owner only)
DELETE /api/params/[id]         — delete (owner only, cascades runs)
POST   /api/params/[id]/fork    — fork to current user

GET    /api/runs                — list runs (filterable)
POST   /api/runs                — queue new run (param set id + test type)
GET    /api/runs/[id]           — get run with summary stats

GET    /api/results/[runId]     — get eclipse results for a run (paginated)

GET    /api/compare?a=<id>&b=<id>&type=solar  — comparison data
```

## File Layout

```
admin/                              # new directory in tychos repo
  package.json
  next.config.ts
  tsconfig.json
  components.json                   # shadcn config
  prisma/
    schema.prisma
  src/
    app/
      layout.tsx                    # root layout with sidebar
      page.tsx                      # dashboard
      parameters/
        page.tsx                    # param list
        [id]/page.tsx               # param detail/editor
      runs/page.tsx
      results/[runId]/page.tsx
      compare/page.tsx
      api/
        auth/register/route.ts
        auth/login/route.ts
        auth/logout/route.ts
        params/route.ts
        params/[id]/route.ts
        params/[id]/fork/route.ts
        runs/route.ts
        runs/[id]/route.ts
        results/[runId]/route.ts
        compare/route.ts
    components/
      sidebar.tsx
      ui/                           # shadcn components
      dashboard/
        stats-cards.tsx
        recent-runs.tsx
        leaderboard.tsx
      parameters/
        param-list.tsx
        param-editor.tsx
        param-form.tsx
      runs/
        run-table.tsx
      results/
        results-table.tsx
      compare/
        compare-view.tsx
        param-diff.tsx
        changed-eclipses.tsx
    lib/
      db.ts                         # Prisma singleton
      auth.ts                       # session helpers
      worker.ts                     # background job runner
      utils.ts
    instrumentation.ts              # starts worker on boot
```

## Dependencies

```
next, react, react-dom
@prisma/client, prisma
shadcn, @base-ui/react
tailwindcss, @tailwindcss/postcss
lucide-react
bcryptjs (password hashing)
date-fns (date formatting)
```

No external job queue (Redis, Bull, etc.). The SQLite-based polling worker is sufficient for sequential test runs.
