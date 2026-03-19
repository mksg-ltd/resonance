"""Ingest endpoint — trigger LRC ingestion pipeline."""

from dataclasses import dataclass
from pathlib import Path

from fastapi import APIRouter, Request
from pydantic import BaseModel
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from lrc_match.chunker import chunk_song
from lrc_match.config import Settings
from lrc_match.embedders.base import EmbeddingProvider

router = APIRouter(prefix="/api")

# Hardcoded until Jellyfin API integration (PRD-04/05)
MUSIC_DIR = Path("/data/media/music/english")


class IngestRequest(BaseModel):
    """Ingest request body."""

    collection: str | None = None
    gap_threshold_sec: float | None = None
    min_chunk_lines: int | None = None
    force: bool = False


class IngestResponse(BaseModel):
    """Ingest response body."""

    files_processed: int
    chunks_created: int
    collection: str
    skipped: int
    model_mismatch: bool = False
    stored_model: str | None = None
    active_model: str | None = None


@dataclass
class IngestResult:
    """Result of an ingestion run."""

    files_processed: int
    chunks_created: int
    skipped: int
    model_mismatch: bool = False
    stored_model: str | None = None


def run_ingest(  # noqa: PLR0913
    qdrant: QdrantClient,
    embedder: EmbeddingProvider,
    settings: Settings,
    *,
    collection: str | None = None,
    gap_threshold_sec: float | None = None,
    min_chunk_lines: int | None = None,
    force: bool = False,
    data_dir: Path | None = None,
) -> IngestResult:
    """Execute ingestion pipeline — reusable by both API route and CLI.

    Parses LRC files, chunks them, embeds with the configured provider,
    and stores vectors + metadata in Qdrant.
    """
    collection = collection or settings.qdrant.collection
    source_dir = data_dir or MUSIC_DIR
    gap_threshold = gap_threshold_sec if gap_threshold_sec is not None else settings.chunking.gap_threshold_sec

    # Check if collection exists and has data
    existing_collections = [c.name for c in qdrant.get_collections().collections]
    if collection in existing_collections and not force:
        info = qdrant.get_collection(collection)
        if info.points_count and info.points_count > 0:
            # Check for model mismatch — warn if active embedder differs from stored
            stored_model = _get_stored_model(qdrant, collection)
            mismatch = stored_model is not None and stored_model != embedder.model_name
            return IngestResult(
                files_processed=0,
                chunks_created=0,
                skipped=0,
                model_mismatch=mismatch,
                stored_model=stored_model,
            )

    # Parse and chunk all LRC files
    chunks_to_embed = []
    skipped = 0
    files_processed = 0

    for lrc_file in sorted(source_dir.glob("*.lrc")):
        lyric = chunk_song(lrc_file, gap_threshold_sec=gap_threshold)
        if not lyric or not lyric.chunks:
            skipped += 1
            continue
        files_processed += 1
        chunks_to_embed.extend(
            {
                "artist": lyric.artist,
                "title": lyric.title,
                "filename": lyric.filename,
                "section": chunk.section_name,
                "position": chunk.position,
                "total_sections": chunk.total_chunks,
                "lyrics": chunk.lyrics,
                "start_sec": chunk.start_sec,
                "duration_sec": chunk.duration_sec,
            }
            for chunk in lyric.chunks
        )

    if not chunks_to_embed:
        return IngestResult(files_processed=0, chunks_created=0, skipped=skipped)

    # Create/recreate collection with provider metadata
    if collection in existing_collections:
        qdrant.delete_collection(collection)

    qdrant.create_collection(
        collection_name=collection,
        vectors_config=VectorParams(size=embedder.dimensions, distance=Distance.COSINE),
    )

    # Store collection metadata as a special point (id=0, empty vector)
    # This lets us know what provider/model was used without external state
    _store_collection_metadata(qdrant, collection, embedder)

    # Embed and upsert in batches
    batch_size = 64
    for i in range(0, len(chunks_to_embed), batch_size):
        batch = chunks_to_embed[i : i + batch_size]
        lyrics_texts = [c["lyrics"] for c in batch]
        vectors = embedder.embed(lyrics_texts)

        points = [
            PointStruct(
                id=i + j + 1,  # Start from 1 (0 is reserved for metadata)
                vector=vec,
                payload={
                    "artist": chunk["artist"],
                    "title": chunk["title"],
                    "filename": chunk["filename"],
                    "section": chunk["section"],
                    "position": chunk["position"],
                    "total_sections": chunk["total_sections"],
                    "lyrics": chunk["lyrics"][:500],
                    "start_sec": chunk["start_sec"],
                    "duration_sec": chunk["duration_sec"],
                },
            )
            for j, (chunk, vec) in enumerate(zip(batch, vectors, strict=True))
        ]

        qdrant.upsert(collection_name=collection, points=points)

    return IngestResult(files_processed=files_processed, chunks_created=len(chunks_to_embed), skipped=skipped)


def _get_stored_model(qdrant: QdrantClient, collection: str) -> str | None:
    """Read the model name from collection metadata point (id=0)."""
    try:
        points = qdrant.retrieve(collection_name=collection, ids=[0])
        if points and points[0].payload and points[0].payload.get("_metadata"):
            return points[0].payload.get("model")
    except Exception:  # noqa: BLE001
        pass
    return None


def _store_collection_metadata(qdrant: QdrantClient, collection: str, embedder: EmbeddingProvider) -> None:
    """Store provider/model/dimensions as a metadata point in the collection."""
    zero_vector = [0.0] * embedder.dimensions
    qdrant.upsert(
        collection_name=collection,
        points=[
            PointStruct(
                id=0,
                vector=zero_vector,
                payload={
                    "_metadata": True,
                    "provider": embedder.provider_name,
                    "model": embedder.model_name,
                    "dimensions": embedder.dimensions,
                },
            )
        ],
    )


@router.post("/ingest", response_model=IngestResponse)
def ingest(body: IngestRequest, request: Request) -> IngestResponse:
    """Trigger LRC ingestion pipeline."""
    collection = body.collection or request.app.state.settings.qdrant.collection
    result = run_ingest(
        qdrant=request.app.state.qdrant,
        embedder=request.app.state.embedder,
        settings=request.app.state.settings,
        collection=body.collection,
        gap_threshold_sec=body.gap_threshold_sec,
        min_chunk_lines=body.min_chunk_lines,
        force=body.force,
    )

    return IngestResponse(
        files_processed=result.files_processed,
        chunks_created=result.chunks_created,
        collection=collection,
        skipped=result.skipped,
        model_mismatch=result.model_mismatch,
        stored_model=result.stored_model,
        active_model=request.app.state.embedder.model_name if result.model_mismatch else None,
    )
