"""Ingest endpoint — trigger LRC ingestion pipeline."""

from dataclasses import dataclass
from pathlib import Path

from fastapi import APIRouter, Request
from pydantic import BaseModel
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from resonance.chunker import chunk_song_data
from resonance.config import Settings
from resonance.embedders import create_embedder_for_name
from resonance.embedders.base import EmbeddingProvider
from resonance.scanner import LibraryScanner

router = APIRouter(prefix="/api")


class IngestRequest(BaseModel):
    """Ingest request body."""

    provider: str  # named provider config from conf.d/ (e.g., "ollama-bge-m3", "vyakyarth")
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
    config_name: str = "",
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
    gap_threshold = gap_threshold_sec if gap_threshold_sec is not None else settings.chunking.gap_threshold_sec
    min_lines = min_chunk_lines if min_chunk_lines is not None else settings.chunking.min_chunk_lines

    print(
        f"Ingest: collection={collection}, provider={embedder.provider_name}, "
        f"model={embedder.model_name} ({embedder.dimensions}d), "
        f"gap={gap_threshold}s, min_lines={min_lines}, force={force}, source={data_dir}"
    )

    # Validate data_dir — required for scanning
    if data_dir is None:
        msg = "data_dir is required — set it in config or pass via --data-dir CLI flag"
        raise ValueError(msg)
    source_dir = data_dir

    # Check if collection exists
    existing_collections = [c.name for c in qdrant.get_collections().collections]
    collection_exists = collection in existing_collections

    if collection_exists and not force:
        # Check for model mismatch
        stored_model = _get_stored_model(qdrant, collection)
        if stored_model is not None and stored_model != embedder.model_name:
            return IngestResult(
                files_processed=0,
                chunks_created=0,
                skipped=0,
                model_mismatch=True,
                stored_model=stored_model,
            )

    # Force mode: delete and recreate
    if force and collection_exists:
        qdrant.delete_collection(collection)
        collection_exists = False

    # Create collection if needed
    if not collection_exists:
        qdrant.create_collection(
            collection_name=collection,
            vectors_config=VectorParams(size=embedder.dimensions, distance=Distance.COSINE),
        )
        _store_collection_metadata(qdrant, collection, embedder, config_name)

    # Get already-ingested audio paths for incremental mode
    existing_paths = _get_existing_audio_paths(qdrant, collection) if collection_exists else set()
    if existing_paths:
        print(f"Incremental mode: {len(existing_paths)} songs already ingested, scanning for new files")

    # Scan library and chunk songs
    chunks_to_embed = []
    skipped = 0
    files_processed = 0

    scanner = LibraryScanner()
    for song in scanner.scan(source_dir):
        audio_path = str(song.audio_path.relative_to(source_dir))
        if audio_path in existing_paths:
            continue
        chunks = chunk_song_data(song, gap_threshold_sec=gap_threshold, min_chunk_lines=min_lines)
        if not chunks:
            skipped += 1
            continue
        files_processed += 1
        chunks_to_embed.extend(
            {
                "artist": song.artist,
                "title": song.title,
                "album": song.album,
                "filename": song.filename,
                "audio_path": audio_path,
                "lyrics_source": song.lyrics_source,
                "section": chunk.section_name,
                "position": chunk.position,
                "total_sections": chunk.total_chunks,
                "lyrics": chunk.lyrics,
                "start_sec": chunk.start_sec,
                "duration_sec": chunk.duration_sec,
            }
            for chunk in chunks
        )

    # Determine starting point ID (after existing points)
    if collection_exists:
        info = qdrant.get_collection(collection)
        next_id = (info.points_count or 0) + 1
    else:
        next_id = 1  # 0 is reserved for metadata

    # Embed and upsert in batches
    batch_size = 64
    for i in range(0, len(chunks_to_embed), batch_size):
        batch = chunks_to_embed[i : i + batch_size]
        lyrics_texts = [c["lyrics"] for c in batch]
        vectors = embedder.embed(lyrics_texts)

        points = [
            PointStruct(
                id=next_id + i + j,
                vector=vec,
                payload={
                    "artist": chunk["artist"],
                    "title": chunk["title"],
                    "album": chunk["album"],
                    "filename": chunk["filename"],
                    "audio_path": chunk["audio_path"],
                    "lyrics_source": chunk["lyrics_source"],
                    "section": chunk["section"],
                    "position": chunk["position"],
                    "total_sections": chunk["total_sections"],
                    "lyrics": chunk["lyrics"],
                    "start_sec": chunk["start_sec"],
                    "duration_sec": chunk["duration_sec"],
                },
            )
            for j, (chunk, vec) in enumerate(zip(batch, vectors, strict=True))
        ]

        qdrant.upsert(collection_name=collection, points=points)

    return IngestResult(files_processed=files_processed, chunks_created=len(chunks_to_embed), skipped=skipped)


def _get_existing_audio_paths(qdrant: QdrantClient, collection: str) -> set[str]:
    """Fetch all audio_path values already stored in the collection."""
    paths: set[str] = set()
    offset = None
    while True:
        results = qdrant.scroll(
            collection_name=collection,
            limit=1000,
            offset=offset,
            with_payload=["audio_path"],
            with_vectors=False,
        )
        points, next_offset = results
        for point in points:
            if point.payload and point.payload.get("audio_path"):
                paths.add(point.payload["audio_path"])
        if next_offset is None:
            break
        offset = next_offset
    return paths


def _get_stored_model(qdrant: QdrantClient, collection: str) -> str | None:
    """Read the model name from collection metadata point (id=0)."""
    try:
        points = qdrant.retrieve(collection_name=collection, ids=[0])
        if points and points[0].payload and points[0].payload.get("_metadata"):
            return points[0].payload.get("model")
    except Exception:  # noqa: BLE001
        pass
    return None


def _store_collection_metadata(
    qdrant: QdrantClient, collection: str, embedder: EmbeddingProvider, config_name: str
) -> None:
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
                    "config_name": config_name,
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
    settings = request.app.state.settings
    collection = body.collection or settings.qdrant.collection
    embedder = create_embedder_for_name(body.provider)

    result = run_ingest(
        qdrant=request.app.state.qdrant,
        embedder=embedder,
        settings=settings,
        config_name=body.provider,
        collection=body.collection,
        gap_threshold_sec=body.gap_threshold_sec,
        min_chunk_lines=body.min_chunk_lines,
        force=body.force,
        data_dir=Path(settings.data_dir) if settings.data_dir else None,
    )

    return IngestResponse(
        files_processed=result.files_processed,
        chunks_created=result.chunks_created,
        collection=collection,
        skipped=result.skipped,
        model_mismatch=result.model_mismatch,
        stored_model=result.stored_model,
        active_model=embedder.model_name if result.model_mismatch else None,
    )
