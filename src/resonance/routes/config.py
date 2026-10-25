"""Config endpoint — read-only current configuration."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from resonance.auth import Principal
from resonance.routes.auth import get_principal

router = APIRouter(prefix="/api")


@router.get("/config")
def get_config(request: Request, _principal: Annotated[Principal, Depends(get_principal)]) -> dict:
    """Return current configuration with secrets redacted."""
    settings = request.app.state.settings
    data = settings.model_dump(mode="json", exclude={"navidrome", "journal_path"})
    data["navidrome"] = {"server_id": settings.navidrome.server_id, "configured": bool(settings.navidrome.base_url)}
    data["embedding"] = {
        "profile": settings.embedding.profile,
        "base_url_configured": bool(settings.embedding.base_url),
        "configured": bool(settings.embedding.base_url or settings.embedding.profile == "openai"),
        "api_key_configured": bool(settings.embedding.api_key and settings.embedding.api_key.get_secret_value()),
    }
    data["authentication_configured"] = bool(settings.navidrome.base_url)
    return data
