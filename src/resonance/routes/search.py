"""Search endpoint — semantic lyric search via Qdrant."""

from fastapi import APIRouter, Request
from pydantic import BaseModel
from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

from resonance.embedders.base import EmbeddingProvider

router = APIRouter(prefix="/api")


class SearchRequest(BaseModel):
    """Search request body."""

    query: str
    artist: str | None = None
    limit: int = 15
    collection: str | None = None


class SearchResult(BaseModel):
    """A single search result."""

    artist: str
    title: str
    score: float
    section: str
    position: int
    total_sections: int
    lyrics: str
    filename: str


class SearchResponse(BaseModel):
    """Search response body."""

    query: str
    results: list[SearchResult]
    total: int


def run_search(  # noqa: PLR0913
    qdrant: QdrantClient,
    embedder: EmbeddingProvider,
    query: str,
    collection: str,
    artist: str | None = None,
    limit: int = 15,
) -> list[SearchResult]:
    """Execute semantic search — reusable by both API route and CLI."""
    query_vector = embedder.embed([query])[0]

    query_filter = None
    if artist:
        query_filter = Filter(must=[FieldCondition(key="artist", match=MatchValue(value=artist))])

    results = qdrant.query_points(
        collection_name=collection,
        query=query_vector,
        query_filter=query_filter,
        limit=limit,
    )

    # Deduplicate by song — keep highest scoring section per artist+title
    seen: dict[str, SearchResult] = {}
    for point in results.points:
        p = point.payload
        key = f"{p['artist']}|{p['title']}"
        result = SearchResult(
            artist=p["artist"],
            title=p["title"],
            score=point.score,
            section=p["section"],
            position=p["position"],
            total_sections=p["total_sections"],
            lyrics=p["lyrics"],
            filename=p["filename"],
        )
        if key not in seen or point.score > seen[key].score:
            seen[key] = result

    return sorted(seen.values(), key=lambda r: r.score, reverse=True)[:limit]


def _get_collection_metadata(qdrant: QdrantClient, collection: str) -> tuple[str | None, str | None]:
    """Read provider and model from collection metadata (point id=0)."""
    try:
        points = qdrant.retrieve(collection_name=collection, ids=[0])
        if points and points[0].payload and points[0].payload.get("_metadata"):
            return points[0].payload.get("provider"), points[0].payload.get("model")
    except Exception:  # noqa: BLE001
        pass
    return None, None


@router.post("/search", response_model=SearchResponse)
def search(body: SearchRequest, request: Request) -> SearchResponse:
    """Semantic lyric search. Auto-selects embedder based on collection metadata."""
    from resonance.embedders import get_embedder_for_provider

    settings = request.app.state.settings
    collection = body.collection or settings.qdrant.collection
    qdrant = request.app.state.qdrant

    # Pick the right embedder for this collection
    stored_provider, stored_model = _get_collection_metadata(qdrant, collection)
    embedder = (
        get_embedder_for_provider(stored_provider, model=stored_model)
        if stored_provider
        else request.app.state.embedder
    )

    results = run_search(
        qdrant=qdrant,
        embedder=embedder,
        query=body.query,
        collection=collection,
        artist=body.artist,
        limit=body.limit,
    )

    return SearchResponse(query=body.query, results=results, total=len(results))
