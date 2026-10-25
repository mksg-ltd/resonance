"""Config endpoint — read-only current configuration."""

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api")


@router.get("/config")
def get_config(request: Request) -> dict:
    """Return current configuration with secrets redacted."""
    settings = request.app.state.settings
    data = settings.model_dump(mode="json", exclude={"navidrome", "api_token", "journal_path"})
    data["navidrome"] = {"server_id": settings.navidrome.server_id, "configured": bool(settings.navidrome.base_url)}
    data["authentication_configured"] = bool(settings.api_token)
    return data
