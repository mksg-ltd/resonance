"""Thin semantic-search HTTP adapter for Navidrome-native collections."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from resonance import embedders
from resonance.application.collections import visible_collections
from resonance.application.indexing import SCHEMA_VERSION
from resonance.application.search import SearchResult, run_search
from resonance.navidrome import NavidromeClient, legacy_source_fingerprint
from resonance.routes.auth import get_navidrome

router = APIRouter(prefix="/api")
Source = Annotated[NavidromeClient, Depends(get_navidrome)]


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    collection: str = Field(min_length=1)
    artist: str | None = None
    limit: int = Field(default=15, ge=1, le=100)


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]
    total: int
    notice: str | None = None


@router.post("/search", response_model=SearchResponse)
def search(body: SearchRequest, request: Request, source: Source) -> SearchResponse:
    qdrant = request.app.state.qdrant
    library_ids = {library.id for library in source.libraries()}
    admin_user = request.app.state.settings.admin_user
    legacy_fingerprint = (
        legacy_source_fingerprint(request.app.state.settings.navidrome.base_url, admin_user)
        if admin_user and request.app.state.settings.navidrome.base_url
        else None
    )
    allowed = visible_collections(
        qdrant,
        source.binding,
        library_ids,
        legacy_fingerprint=legacy_fingerprint,
    )
    authorized = next((item for item in allowed if item.name == body.collection), None)
    if authorized is None:
        raise HTTPException(status_code=404, detail="Collection not found")
    metadata = authorized.metadata
    config_name = metadata.get("config_name")
    if not config_name:
        raise HTTPException(
            status_code=400, detail="Collection has no embedding profile; reingest the Navidrome library"
        )
    binding = source.binding if metadata.get("schema_version") == SCHEMA_VERSION else None
    results = run_search(
        qdrant,
        embedders.resolve_embedder(config_name, request.app.state.settings.embedding),
        body.query,
        body.collection,
        body.artist,
        body.limit,
        source_binding=binding,
    )
    return SearchResponse(
        query=body.query,
        results=results,
        total=len(results),
        notice="Fewer complete songs found within the search window" if len(results) < body.limit else None,
    )
