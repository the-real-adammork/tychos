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


app = FastAPI(lifespan=lifespan, redirect_slashes=False)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from server.api.auth_routes import router as auth_router  # noqa: E402
from server.api.params_routes import router as params_router  # noqa: E402
from server.api.runs_routes import router as runs_router  # noqa: E402
from server.api.results_routes import router as results_router  # noqa: E402
from server.api.compare_routes import router as compare_router  # noqa: E402
from server.api.dashboard_routes import router as dashboard_router  # noqa: E402

app.include_router(auth_router)
app.include_router(params_router)
app.include_router(runs_router)
app.include_router(results_router)
app.include_router(compare_router)
app.include_router(dashboard_router)

from fastapi.responses import FileResponse

# Serve built admin SPA in production (admin/dist/ exists after `npm run build`)
_admin_dist = Path(__file__).parent.parent / "admin" / "dist"
if _admin_dist.is_dir():
    app.mount("/assets", StaticFiles(directory=_admin_dist / "assets"), name="static-assets")

    @app.get("/{path:path}")
    async def spa_fallback(path: str):
        """Serve index.html for all non-API routes (SPA client routing)."""
        return FileResponse(_admin_dist / "index.html")
