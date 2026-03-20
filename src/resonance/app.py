"""FastAPI application factory."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from qdrant_client import QdrantClient

from resonance.config import Settings
from resonance.routes.collections import router as collections_router
from resonance.routes.config import router as config_router
from resonance.routes.health import router as health_router
from resonance.routes.ingest import router as ingest_router
from resonance.routes.playlists import router as playlists_router
from resonance.routes.search import router as search_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Initialize shared resources on startup, clean up on shutdown."""
    settings: Settings = app.state.settings
    qdrant = QdrantClient(
        url=settings.qdrant.url,
        api_key=settings.qdrant.api_key.get_secret_value() if settings.qdrant.api_key else None,
    )
    app.state.qdrant = qdrant

    yield
    qdrant.close()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    if settings is None:
        settings = Settings()

    docs_url = "/docs" if settings.serve_docs else None
    redoc_url = "/redoc" if settings.serve_docs else None

    app = FastAPI(
        title="resonance",
        description="Semantic search over song lyrics",
        version="0.1.0",
        docs_url=docs_url,
        redoc_url=redoc_url,
        lifespan=lifespan,
    )
    app.state.settings = settings

    # CORS — allow static UI to call the API
    if settings.debug:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # Register routes
    app.include_router(health_router)
    app.include_router(search_router)
    app.include_router(ingest_router)
    app.include_router(config_router)
    app.include_router(collections_router)
    app.include_router(playlists_router)

    # Serve static UI files (if ui/ directory exists)
    ui_dir = Path(__file__).resolve().parent.parent.parent / "ui"
    if ui_dir.is_dir():
        app.mount("/ui", StaticFiles(directory=ui_dir, html=True), name="ui")

    return app


def cli() -> None:
    """CLI entry point for resonance-server command."""
    settings = Settings()
    uvicorn.run(
        "resonance.app:create_app",
        factory=True,
        host="0.0.0.0",  # noqa: S104
        port=8000,
        reload=settings.debug,
        log_level="info",
    )


def dev() -> None:
    """CLI entry point for local development — always enables debug + reload + docs."""
    import os

    os.environ["RESONANCE__DEBUG"] = "true"
    os.environ["RESONANCE__SERVE_DOCS"] = "true"
    uvicorn.run(
        "resonance.app:create_app",
        factory=True,
        host="0.0.0.0",  # noqa: S104
        port=8000,
        reload=True,
        log_level="info",
    )
