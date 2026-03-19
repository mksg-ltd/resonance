"""Config endpoint — read-only current configuration."""

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api")


@router.get("/config")
def get_config(request: Request) -> dict:
    """Return current configuration with secrets redacted."""
    settings = request.app.state.settings
    return settings.model_dump(mode="json")
