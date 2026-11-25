"""FastAPI application entrypoint for PhaseSight backend."""

from __future__ import annotations

from contextlib import asynccontextmanager
import os
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.deps import get_manager, get_storage
from backend.routes.assets import router as assets_router
from backend.routes.baselines import router as baselines_router
from backend.routes.health import router as health_router
from backend.routes.runs import router as runs_router
from backend.routes.sessions import router as sessions_router
from backend.routes.videos import router as videos_router
from backend.ws import router as ws_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application lifespan resources."""
    # Startup: initialize storage and session manager
    storage = get_storage()
    manager = get_manager()
    yield
    # Shutdown: clean up background threads and database handles
    manager.shutdown()
    storage.close()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="PhaseSight Vibration Monitoring Engine API",
        version="1.0.0",
        description="REST and WebSocket API for subpixel phase-correlation vibration monitoring.",
        lifespan=lifespan,
    )

    # CORS configuration
    cors_env = os.environ.get("PHASESIGHT_CORS_ORIGINS")
    if cors_env:
        origins = [o.strip() for o in cors_env.split(",") if o.strip()]
    else:
        origins = [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:[0-9]+)?$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # REST routers under /api/v1
    app.include_router(health_router, prefix="/api/v1")
    app.include_router(assets_router, prefix="/api/v1")
    app.include_router(videos_router, prefix="/api/v1")
    app.include_router(runs_router, prefix="/api/v1")
    app.include_router(baselines_router, prefix="/api/v1")
    app.include_router(sessions_router, prefix="/api/v1")

    # WebSocket router
    app.include_router(ws_router)

    @app.get("/")
    def root():
        return {
            "name": "PhaseSight API",
            "version": "1.0.0",
            "docs": "/docs",
            "health": "/api/v1/health",
        }

    return app


app = create_app()
