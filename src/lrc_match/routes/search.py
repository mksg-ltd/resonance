"""Search endpoint — semantic lyric search via Qdrant."""

from fastapi import APIRouter, Request
from pydantic import BaseModel
from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

from lrc_match.embedders.base import EmbeddingProvider

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


@router.post("/search", response_model=SearchResponse)
def search(body: SearchRequest, request: Request) -> SearchResponse:
    """Semantic lyric search."""
    settings = request.app.state.settings
    collection = body.collection or settings.qdrant.collection
    embedder = request.app.state.embedder

    results = run_search(
        qdrant=request.app.state.qdrant,
        embedder=embedder,
        query=body.query,
        collection=collection,
        artist=body.artist,
        limit=body.limit,
    )

    return SearchResponse(query=body.query, results=results, total=len(results))
