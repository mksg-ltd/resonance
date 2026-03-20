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

from resonance.config import Settings, load_settings
from resonance.embedders import create_embedder
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

    # Initialize embedder (may fail if provider config missing — that's OK at startup)
    try:
        app.state.embedder = create_embedder(settings)
    except ValueError:
        logger.warning("Embedder not configured — search and ingest endpoints will fail until provider is set up")
        app.state.embedder = None

    yield
    qdrant.close()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    if settings is None:
        settings = load_settings()

    docs_url = "/docs" if settings.server.debug else None
    redoc_url = "/redoc" if settings.server.debug else None

    app = FastAPI(
        title="resonance",
        description="Semantic search over song lyrics",
        version="0.1.0",
        docs_url=docs_url,
        redoc_url=redoc_url,
        lifespan=lifespan,
    )
    app.state.settings = settings

    # CORS — allow static UI and Jellyfin plugin to call the API
    if settings.server.debug:
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
    settings = load_settings()
    uvicorn.run(
        "resonance.app:create_app",
        factory=True,
        host=settings.server.host,
        port=settings.server.port,
        reload=settings.server.debug,
        log_level="info",
    )


def dev() -> None:
    """CLI entry point for local development — always enables debug + reload."""
    import os

    os.environ["RESONANCE__SERVER__DEBUG"] = "true"
    settings = load_settings()
    uvicorn.run(
        "resonance.app:create_app",
        factory=True,
        host=settings.server.host,
        port=settings.server.port,
        reload=True,
        log_level="info",
    )
