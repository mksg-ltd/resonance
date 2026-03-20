"""Health check endpoint."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/health")
def health(request: Request) -> JSONResponse:
    """Check service health — Qdrant connectivity and config status."""
    qdrant = request.app.state.qdrant

    try:
        qdrant.get_collections()
        qdrant_status = "connected"
        status_code = 200
    except Exception:  # noqa: BLE001
        qdrant_status = "unreachable"
        status_code = 503

    return JSONResponse(
        status_code=status_code,
        content={
            "status": "healthy" if status_code == 200 else "unhealthy",
            "qdrant": qdrant_status,
        },
    )
