"""Config endpoint — read-only current configuration."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from resonance.auth import Principal
from resonance.embedding_profiles import embedding_profiles
from resonance.routes.auth import get_principal, require_admin

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


@router.get("/embedding-profiles")
def list_embedding_profiles(
    request: Request,
    _admin: Annotated[Principal, Depends(require_admin)],
) -> list[dict[str, str | int | bool | None]]:
    """List supported, non-secret embedding profile metadata for admin setup."""
    default_profile = request.app.state.settings.embedding.profile
    return [
        {
            "id": profile_id,
            "model_id": profile.model_id,
            "dimensions": profile.dimensions,
            "protocol": profile.protocol,
            "revision": profile.revision,
            "is_default": profile_id == default_profile,
        }
        for profile_id, profile in sorted(embedding_profiles().items())
    ]
