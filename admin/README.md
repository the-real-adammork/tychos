# Tychos Admin UI

The web admin for the Tychos eclipse prediction test suite. A single-page React application that talks to the FastAPI backend in `../server/`.

## Stack

- **[Vite](https://vite.dev/)** for dev server and bundling
- **React 19** with TypeScript
- **[React Router](https://reactrouter.com/) v7** for client-side routing
- **[Tailwind CSS](https://tailwindcss.com/)** for styling
- **[Base UI](https://base-ui.com/) + [shadcn/ui](https://ui.shadcn.com/)** for primitives (Card, Table, Select, Dialog, etc.) under `src/components/ui/`
- **[date-fns](https://date-fns.org/)** for date formatting

This is **not** a Next.js project despite some leftover files in `public/`.

## Development

```bash
npm install
npm run dev   # http://localhost:5173, proxies /api to localhost:8000
```

The dev server expects the FastAPI backend to be running at `http://localhost:8000`. The Vite proxy forwards `/api/*` requests to the backend, so cookies and CORS work automatically. Start everything together from the repo root with `./dev.sh`.

## Build

```bash
npm run build
```

Produces `dist/`, which the FastAPI server picks up at startup and serves at the root path with a SPA fallback to `index.html` (see `server/app.py`). After building, you can hit the production-style URL by going through the API server alone instead of the Vite dev server.

## Project Layout

```
src/
├── App.tsx                    # Router + auth provider
├── main.tsx                   # Vite entry
├── pages/                     # Route components
│   ├── DashboardPage.tsx
│   ├── ParametersPage.tsx     # /parameters
│   ├── ParamDetailPage.tsx    # /parameters/:id
│   ├── ParamVersionDetailPage.tsx  # /parameters/:id/versions/:versionId
│   ├── ParamEditPage.tsx
│   ├── RunsPage.tsx
│   ├── ResultsPage.tsx        # /results/:runId — table view
│   ├── ResultDetailPage.tsx   # /results/:runId/:resultId — 3-diagram view
│   ├── DatasetsPage.tsx
│   ├── DatasetDetailPage.tsx  # /datasets/:slug
│   ├── EclipseCatalogDetailPage.tsx  # /datasets/:slug/:eclipseId
│   ├── ComparePage.tsx        # /compare?a=N&b=N
│   ├── LoginPage.tsx
│   └── RegisterPage.tsx
├── components/
│   ├── ui/                    # shadcn/ui primitives
│   ├── eclipse/               # Shared eclipse diagrams
│   │   ├── predicted-diagram.tsx
│   │   └── saros-context.tsx
│   ├── results/results-table.tsx
│   ├── runs/run-table.tsx
│   ├── compare/{compare-view, changed-eclipses, param-diff}.tsx
│   ├── parameters/{param-list, param-form, param-editor, param-viewer}.tsx
│   ├── dashboard/{stats-cards, leaderboard, recent-runs, dataset-summary}.tsx
│   └── sidebar.tsx
└── lib/utils.ts
```

## URL State Conventions

Most table views encode their filter and sort state in the URL via `useSearchParams`, so they're bookmarkable and survive reloads:

- `/results/:runId?page=1&type=total&group=saros&sort_by=tychos_error_arcmin&sort_dir=desc&saros=145`
- `/datasets/:slug?page=1&catalog=total&saros=145`
- `/compare?a=1&b=2&dataset=solar_eclipse`

## Auth

Cookie-based sessions issued by the backend. The Vite dev server proxies through `/api`, and the SPA reads `/api/auth/me` on mount to determine the logged-in user. There is no client-side token; the cookie is `httponly`.
