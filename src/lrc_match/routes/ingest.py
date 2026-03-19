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

    force: bool = False


class IngestResponse(BaseModel):
    """Ingest response body."""

    files_processed: int
    chunks_created: int
    collection: str
    skipped: int


@dataclass
class IngestResult:
    """Result of an ingestion run."""

    files_processed: int
    chunks_created: int
    skipped: int


def run_ingest(
    qdrant: QdrantClient,
    embedder: EmbeddingProvider,
    settings: Settings,
    *,
    force: bool = False,
    data_dir: Path | None = None,
) -> IngestResult:
    """Execute ingestion pipeline — reusable by both API route and CLI.

    Parses LRC files, chunks them, embeds with the configured provider,
    and stores vectors + metadata in Qdrant.
    """
    collection = settings.qdrant.collection
    source_dir = data_dir or MUSIC_DIR
    gap_threshold = settings.chunking.gap_threshold_sec

    # Check if collection exists and has data
    existing_collections = [c.name for c in qdrant.get_collections().collections]
    if collection in existing_collections and not force:
        info = qdrant.get_collection(collection)
        if info.points_count and info.points_count > 0:
            return IngestResult(files_processed=0, chunks_created=0, skipped=0)

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
    result = run_ingest(
        qdrant=request.app.state.qdrant,
        embedder=request.app.state.embedder,
        settings=request.app.state.settings,
        force=body.force,
    )

    return IngestResponse(
        files_processed=result.files_processed,
        chunks_created=result.chunks_created,
        collection=request.app.state.settings.qdrant.collection,
        skipped=result.skipped,
    )
