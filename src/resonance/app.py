"""FastAPI application factory."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from qdrant_client import QdrantClient
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import Scope

from resonance.auth import AuthRuntime
from resonance.config import Settings
from resonance.embedders import close_embedders
from resonance.errors import ApplicationError
from resonance.routes.auth import router as auth_router
from resonance.routes.collections import router as collections_router
from resonance.routes.config import router as config_router
from resonance.routes.health import router as health_router
from resonance.routes.ingest import router as ingest_router
from resonance.routes.navidrome import router as navidrome_router
from resonance.routes.search import router as search_router

logger = logging.getLogger(__name__)


class SPAStaticFiles(StaticFiles):
    """Serve the app entry point for frontend routes unknown to the asset server."""

    async def get_response(self, path: str, scope: Scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as error:
            if error.status_code != 404:
                raise
            return await super().get_response("index.html", scope)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Initialize shared resources on startup, clean up on shutdown."""
    settings: Settings = app.state.settings
    qdrant = QdrantClient(
        url=settings.qdrant.url,
        api_key=settings.qdrant.api_key.get_secret_value() if settings.qdrant.api_key else None,
    )
    app.state.qdrant = qdrant

    try:
        yield
    finally:
        app.state.auth_runtime.sessions.clear()
        qdrant.close()
        close_embedders()


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
        openapi_url="/openapi.json" if settings.serve_docs else None,
        docs_url=docs_url,
        redoc_url=redoc_url,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.auth_runtime = AuthRuntime(settings.admin_user)

    @app.exception_handler(ApplicationError)
    async def application_error(_request: Request, error: ApplicationError) -> JSONResponse:
        return JSONResponse(status_code=error.status, content={"detail": str(error), "code": error.code})

    # Register routes
    app.include_router(auth_router)
    app.include_router(health_router)
    app.include_router(search_router)
    app.include_router(ingest_router)
    app.include_router(config_router)
    app.include_router(collections_router)
    app.include_router(navidrome_router)

    # Serve static UI files (if ui/ directory exists)
    ui_dir = Path(__file__).resolve().parent.parent.parent / "ui"
    if ui_dir.is_dir():
        app.mount("/ui", StaticFiles(directory=ui_dir, html=True), name="ui")

    vue_dir = Path(__file__).resolve().parent / "static" / "app"
    if vue_dir.is_dir():
        app.mount("/app", SPAStaticFiles(directory=vue_dir, html=True), name="app")

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
        proxy_headers=True,
        forwarded_allow_ips=settings.trusted_proxy_ips,
    )


def dev() -> None:
    """CLI entry point for local development — always enables debug + reload + docs."""
    import os

    os.environ["RESONANCE__DEBUG"] = "true"
    os.environ["RESONANCE__SERVE_DOCS"] = "true"
    uvicorn.run(
        "resonance.app:create_app",
        factory=True,
        host="127.0.0.1",
        port=8000,
        reload=True,
        log_level="info",
        proxy_headers=False,
    )
