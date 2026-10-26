"""Navidrome-to-Qdrant ingestion independent of HTTP and CLI transports."""

from collections.abc import Callable
from dataclasses import dataclass

from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

from resonance.application.indexing import (
    collection_name,
    desired_metadata,
    ensure_collection,
    lyric_hash,
    song_state,
    track_points,
    vectors_checked,
)
from resonance.chunker import chunk_song_data
from resonance.config import Settings
from resonance.embedders.base import EmbeddingProvider
from resonance.errors import ApplicationError, external_errors, fail
from resonance.navidrome import NavidromeClient


@dataclass
class IngestResult:
    collection: str
    tracks_seen: int = 0
    tracks_processed: int = 0
    tracks_unchanged: int = 0
    sections_written: int = 0
    skipped: int = 0
    missing_lyrics: int = 0
    unsynced_lyrics: int = 0
    enumeration_complete: bool = False
    cancelled: bool = False


@dataclass(frozen=True)
class IngestProgress:
    """Safe aggregate counters; deliberately excludes track metadata and identifiers."""

    tracks_seen: int
    tracks_processed: int
    tracks_unchanged: int
    sections_written: int
    skipped: int
    missing_lyrics: int
    unsynced_lyrics: int


@external_errors("Ingestion interrupted; completed writes are retained. Retry unchanged input to resume")
def run_ingest(  # noqa: PLR0913, PLR0915
    qdrant: QdrantClient,
    embedder: EmbeddingProvider,
    settings: Settings,
    *,
    source: NavidromeClient,
    library_id: str,
    config_name: str,
    collection: str | None = None,
    batch_size: int = 32,
    gap_threshold_sec: float | None = None,
    min_chunk_lines: int | None = None,
    max_tracks: int | None = None,
    progress: Callable[[IngestProgress], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> IngestResult:
    """Index absent songs or repair identical partial writes; never prune/recreate."""
    if not library_id.strip() or batch_size < 1 or (max_tracks is not None and max_tracks < 1):
        fail("Library, batch size, and track limit must be valid")
    gap = settings.chunking.gap_threshold_sec if gap_threshold_sec is None else gap_threshold_sec
    minimum = settings.chunking.min_chunk_lines if min_chunk_lines is None else min_chunk_lines
    desired = desired_metadata(
        source.binding,
        library_id,
        embedder,
        config_name,
        gap_threshold_sec=gap,
        min_chunk_lines=minimum,
        language=source.config.lyrics_language,
    )
    collection = collection or collection_name(
        source.config.server_id, library_id, embedder.model_name, desired["index_fingerprint"]
    )
    metadata = ensure_collection(qdrant, collection, desired)
    result = IngestResult(collection)

    def report() -> None:
        if progress is not None:
            progress(
                IngestProgress(
                    tracks_seen=result.tracks_seen,
                    tracks_processed=result.tracks_processed,
                    tracks_unchanged=result.tracks_unchanged,
                    sections_written=result.sections_written,
                    skipped=result.skipped,
                    missing_lyrics=result.missing_lyrics,
                    unsynced_lyrics=result.unsynced_lyrics,
                )
            )

    for discovered in source.tracks(library_id):
        if should_stop is not None and should_stop():
            result.cancelled = True
            report()
            return result
        if max_tracks is not None and result.tracks_seen >= max_tracks:
            return result
        result.tracks_seen += 1
        if discovered.source_id != metadata["source_id"] or discovered.library_id != library_id:
            fail("Source returned a track outside the selected scope", code="scope_mismatch", status=502)
        track = source.lyrics(discovered)
        if track.lyrics_status != "synced":
            result.skipped += 1
            result.missing_lyrics += track.lyrics_status in {"missing", "empty", "language_unavailable"}
            result.unsynced_lyrics += track.lyrics_status == "unsynced"
            report()
            continue
        chunks = chunk_song_data(track, gap_threshold_sec=gap, min_chunk_lines=minimum)
        if not chunks:
            result.skipped += 1
            report()
            continue
        content_hash = lyric_hash(track)
        expected = track_points(metadata, track, chunks, content_hash)
        state = song_state(qdrant, collection, metadata, track.song_id)
        if state.records and (
            not state.coherent
            or state.lyrics_hash != content_hash
            or state.records[0].payload["total_sections"] != len(expected)
        ):
            fail(
                "Song content or stored sections changed; use a new collection until refresh is supported",
                code="refresh_required",
                status=409,
            )
        if state.complete:
            result.tracks_unchanged += 1
            report()
            continue
        for start in range(0, len(expected), batch_size):
            if should_stop is not None and should_stop():
                result.cancelled = True
                report()
                return result
            batch = expected[start : start + batch_size]
            try:
                vectors = vectors_checked(
                    embedder.embed([row["payload"]["lyrics"] for row in batch]), len(batch), embedder.dimensions
                )
            except ApplicationError:
                raise
            except Exception:  # noqa: BLE001 -- don't expose provider request data in default errors
                fail("Embedding request failed", code="embedding_unavailable", status=502)
            points = [
                PointStruct(id=row["id"], vector=vector, payload=row["payload"])
                for row, vector in zip(batch, vectors, strict=True)
            ]
            qdrant.upsert(collection_name=collection, points=points, wait=True)
            result.sections_written += len(points)
            report()
        if not song_state(qdrant, collection, metadata, track.song_id).complete:
            fail("Song section write did not verify as complete", code="index_incomplete", status=502)
        result.tracks_processed += 1
        report()
    result.enumeration_complete = True
    return result
