"""Thin semantic-search HTTP adapter for Navidrome-native collections."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from resonance import embedders
from resonance.application.indexing import SCHEMA_VERSION, read_metadata
from resonance.application.search import SearchResult, run_search
from resonance.navidrome import source_binding

router = APIRouter(prefix="/api")


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
def search(body: SearchRequest, request: Request) -> SearchResponse:
    qdrant = request.app.state.qdrant
    metadata = read_metadata(qdrant, body.collection)
    config_name = metadata.get("config_name")
    if not config_name:
        raise HTTPException(
            status_code=400, detail="Collection has no embedding profile; reingest the Navidrome library"
        )
    binding = (
        source_binding(request.app.state.settings.navidrome)
        if metadata.get("schema_version") == SCHEMA_VERSION
        else None
    )
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
