"""Caller-scoped collection listing and admin-only deletion."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from resonance.application.collections import visible_collections
from resonance.auth import Principal
from resonance.errors import ApplicationError
from resonance.navidrome import NavidromeClient, legacy_source_fingerprint
from resonance.routes.auth import get_navidrome, require_admin

router = APIRouter(prefix="/api")
Source = Annotated[NavidromeClient, Depends(get_navidrome)]


class CollectionInfo(BaseModel):
    """A collection summary visible to the authenticated Navidrome user."""

    name: str
    points_count: int
    provider: str | None = None
    model: str | None = None
    dimensions: int | None = None
    source_id: str
    library_id: str
    index_fingerprint: str


def _visible(request: Request, source: NavidromeClient):
    libraries = {library.id for library in source.libraries()}
    admin_user = request.app.state.settings.admin_user
    legacy_fingerprint = (
        legacy_source_fingerprint(request.app.state.settings.navidrome.base_url, admin_user)
        if admin_user and request.app.state.settings.navidrome.base_url
        else None
    )
    return visible_collections(
        request.app.state.qdrant,
        source.binding,
        libraries,
        legacy_fingerprint=legacy_fingerprint,
    )


@router.get("/collections", response_model=list[CollectionInfo])
def list_collections(request: Request, source: Source) -> list[CollectionInfo]:
    """List only collections in libraries currently visible to this caller."""
    return [
        CollectionInfo(
            name=item.name,
            points_count=item.points_count,
            provider=item.metadata.get("provider"),
            model=item.metadata.get("model"),
            dimensions=item.metadata.get("dimensions"),
            source_id=item.metadata["source_id"],
            library_id=item.metadata["library_id"],
            index_fingerprint=item.metadata["index_fingerprint"],
        )
        for item in _visible(request, source)
    ]


@router.delete("/collections/{name}")
def delete_collection(
    name: str,
    request: Request,
    source: Source,
    _admin: Annotated[Principal, Depends(require_admin)],
) -> dict[str, str]:
    """Delete an indexed collection only when it belongs to an admin-visible library."""
    if name not in {item.name for item in _visible(request, source)}:
        raise HTTPException(status_code=404, detail="Collection not found")
    try:
        request.app.state.qdrant.delete_collection(name)
    except Exception:  # noqa: BLE001 -- Qdrant SDK boundary
        msg = "Cannot delete collection"
        raise ApplicationError(msg, code="index_unavailable", status=502) from None
    return {"deleted": name}
