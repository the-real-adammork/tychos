"""FastAPI application."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from server.db import init_db
from server.worker import start_worker


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    start_worker()
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from server.api.auth_routes import router as auth_router  # noqa: E402
app.include_router(auth_router)
