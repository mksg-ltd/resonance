"""Shared lyric search, with native recording identity and legacy read compatibility."""

from dataclasses import dataclass

from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

from resonance.application.indexing import (
    embedding_profile,
    read_metadata,
    section_filter,
    song_state,
    validate_binding,
    vectors_checked,
)
from resonance.embedders.base import EmbeddingProvider
from resonance.errors import external_errors, fail


@dataclass
class SearchResult:
    artist: str
    title: str
    score: float
    section: str
    position: int
    total_sections: int
    lyrics: str
    filename: str = ""
    audio_path: str = ""
    lyrics_source: str = "sidecar_lrc"
    album: str | None = None
    source_id: str | None = None
    library_id: str | None = None
    song_id: str | None = None
    start_sec: float | None = None
    duration_sec: float | None = None


def _legacy_search(  # noqa: PLR0913
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
        if not p or p.get("_metadata"):
            continue
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
            filename=p.get("filename", ""),
            audio_path=p.get("audio_path", ""),
            lyrics_source=p.get("lyrics_source", "sidecar_lrc"),
        )
        if key not in seen or point.score > seen[key].score:
            seen[key] = result

    return sorted(seen.values(), key=lambda r: r.score, reverse=True)[:limit]


@external_errors("Search dependency failed")
def run_search(  # noqa: PLR0913
    qdrant: QdrantClient,
    embedder: EmbeddingProvider,
    query: str,
    collection: str,
    artist: str | None = None,
    limit: int = 15,
    *,
    source_binding: dict[str, str] | None = None,
) -> list[SearchResult]:
    """Search native complete recordings, retaining legacy collection read behavior."""
    if not query.strip() or not 1 <= limit <= 100:
        fail("A nonempty query and limit between 1 and 100 are required")
    metadata = read_metadata(qdrant, collection)
    if metadata.get("schema_version") is None:
        if metadata.get("model") and metadata["model"] != embedder.model_name:
            fail("Collection model differs from the active embedder", code="collection_incompatible", status=409)
        return _legacy_search(qdrant, embedder, query, collection, artist, limit)
    if source_binding is None:
        fail("Native search requires the configured source binding", code="not_configured", status=503)
    validate_binding(metadata, source_binding, embedding_profile(embedder))
    vector = vectors_checked(embedder.embed([query]), 1, embedder.dimensions)[0]
    query_filter = section_filter(metadata)
    if artist:
        query_filter.must.append(FieldCondition(key="artist", match=MatchValue(value=artist)))
    window = max(limit * 4, 32)
    eligible: dict[str, bool] = {}
    while True:
        hits = qdrant.query_points(
            collection_name=collection, query=vector, query_filter=query_filter, limit=window
        ).points
        results = {}
        for point in hits:
            payload = point.payload or {}
            song_id = payload.get("song_id")
            if not isinstance(song_id, str):
                continue
            if song_id not in eligible:
                eligible[song_id] = song_state(qdrant, collection, metadata, song_id).complete
            if not eligible[song_id] or song_id in results:
                continue
            results[song_id] = SearchResult(
                artist=payload["artist"],
                title=payload["title"],
                album=payload.get("album"),
                score=point.score,
                section=payload["section"],
                position=payload["position"],
                total_sections=payload["total_sections"],
                lyrics=payload["lyrics"],
                lyrics_source="navidrome",
                source_id=payload["source_id"],
                library_id=payload["library_id"],
                song_id=song_id,
                start_sec=payload.get("start_sec"),
                duration_sec=payload.get("duration_sec"),
            )
        ranked = sorted(results.values(), key=lambda item: (-item.score, item.song_id))
        if len(ranked) >= limit or len(hits) < window or window >= 4096:
            return ranked[:limit]
        window = min(window * 2, 4096)
