"""Search endpoint — semantic lyric search via Qdrant."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

from resonance.embedders.base import EmbeddingProvider

router = APIRouter(prefix="/api")


class SearchRequest(BaseModel):
    """Search request body."""

    query: str
    collection: str  # Qdrant collection name
    artist: str | None = None
    limit: int = 15


class SearchResult(BaseModel):
    """A single search result."""

    artist: str
    title: str
    album: str | None = None
    score: float
    section: str
    position: int
    total_sections: int
    lyrics: str
    filename: str
    audio_path: str = ""
    lyrics_source: str = "sidecar_lrc"


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
            album=p.get("album"),
            score=point.score,
            section=p["section"],
            position=p["position"],
            total_sections=p["total_sections"],
            lyrics=p["lyrics"],
            filename=p["filename"],
            audio_path=p.get("audio_path", ""),
            lyrics_source=p.get("lyrics_source", "sidecar_lrc"),
        )
        if key not in seen or point.score > seen[key].score:
            seen[key] = result

    return sorted(seen.values(), key=lambda r: r.score, reverse=True)[:limit]


def _get_collection_config_name(qdrant: QdrantClient, collection: str) -> str | None:
    """Read the provider config name from collection metadata (point id=0)."""
    try:
        points = qdrant.retrieve(collection_name=collection, ids=[0])
        if points and points[0].payload and points[0].payload.get("_metadata"):
            return points[0].payload.get("config_name")
    except Exception:  # noqa: BLE001
        pass
    return None


@router.post("/search", response_model=SearchResponse)
def search(body: SearchRequest, request: Request) -> SearchResponse:
    """Semantic lyric search. Auto-selects embedder based on collection metadata."""
    from resonance.embedders import create_embedder_for_name

    collection = body.collection
    qdrant = request.app.state.qdrant

    # Pick the right embedder for this collection
    config_name = _get_collection_config_name(qdrant, collection)
    if not config_name:
        msg = f"Collection '{collection}' has no config_name in metadata. Re-ingest with --provider to fix."
        raise HTTPException(status_code=400, detail=msg)

    embedder = create_embedder_for_name(config_name)

    results = run_search(
        qdrant=qdrant,
        embedder=embedder,
        query=body.query,
        collection=collection,
        artist=body.artist,
        limit=body.limit,
    )

    return SearchResponse(query=body.query, results=results, total=len(results))
