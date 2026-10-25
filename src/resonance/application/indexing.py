"""Qdrant schema, deterministic identities, and section-completeness checks."""

import hashlib
import json
import math
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID, uuid4, uuid5

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, FieldCondition, Filter, MatchValue, PointStruct, VectorParams

from resonance.embedders.base import EmbeddingProvider
from resonance.errors import fail
from resonance.models import LrcChunk, Track

SCHEMA_VERSION = 2
POINT_NAMESPACE = UUID("02ad32ea-c49c-4ee8-8533-fc647470b5b7")
MAX_SONG_SECTIONS = 4096


def canonical(value: Any) -> str:
    """Versioned callers use a common finite, Unicode-normalized JSON encoding."""

    def normalize(item: Any) -> Any:
        if isinstance(item, str):
            return unicodedata.normalize("NFC", item)
        if isinstance(item, list | tuple):
            return [normalize(part) for part in item]
        if isinstance(item, dict):
            return {key: normalize(part) for key, part in item.items()}
        return item

    return json.dumps(normalize(value), sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def embedding_profile(embedder: EmbeddingProvider) -> dict[str, Any]:
    profile = getattr(embedder, "profile", None)
    if not isinstance(profile, dict):
        profile = {"provider": embedder.provider_name, "model": embedder.model_name, "dimensions": embedder.dimensions}
    if profile.get("dimensions_verified") is False:
        fail("Configure known output dimensions for this embedding model", code="invalid_configuration", status=503)
    endpoint_value = profile.get("endpoint", "")
    if not isinstance(endpoint_value, str):
        fail("Embedding endpoint must be a string", code="invalid_configuration", status=503)
    endpoint = urlsplit(endpoint_value)
    if any((endpoint.username, endpoint.password, endpoint.query, endpoint.fragment)):
        fail(
            "Embedding endpoints must not contain URL credentials or query secrets",
            code="invalid_configuration",
            status=503,
        )
    return profile


def vectors_checked(vectors: list[list[float]], count: int, dimensions: int) -> list[list[float]]:
    if len(vectors) != count or any(
        len(vector) != dimensions or any(not math.isfinite(value) for value in vector) for vector in vectors
    ):
        fail(
            "Embedding output count, dimensions, or numeric values do not match", code="invalid_embeddings", status=502
        )
    return vectors


def read_metadata(qdrant: QdrantClient, collection: str) -> dict[str, Any]:
    try:
        points = qdrant.retrieve(collection_name=collection, ids=[0], with_payload=True, with_vectors=False)
    except Exception:  # noqa: BLE001 -- SDK boundary; never return raw remote errors
        fail("Cannot read collection metadata", code="index_unavailable", status=502)
    if not points or not points[0].payload or not points[0].payload.get("_metadata"):
        fail("Collection has no compatible metadata; use a new collection", code="collection_incompatible", status=409)
    return points[0].payload


def desired_metadata(  # noqa: PLR0913
    binding: dict[str, str],
    library_id: str,
    embedder: EmbeddingProvider,
    config_name: str,
    *,
    gap_threshold_sec: float,
    min_chunk_lines: int,
    language: str | None,
) -> dict[str, Any]:
    if not math.isfinite(gap_threshold_sec) or gap_threshold_sec <= 0 or min_chunk_lines < 1:
        fail("Invalid chunking settings")
    profile = embedding_profile(embedder)
    options = {"gap_threshold_sec": float(gap_threshold_sec), "min_chunk_lines": min_chunk_lines, "language": language}
    return {
        "_metadata": True,
        "kind": "collection_metadata",
        "schema_version": SCHEMA_VERSION,
        **binding,
        "library_id": library_id,
        "config_name": config_name,
        "provider": embedder.provider_name,
        "model": embedder.model_name,
        "dimensions": embedder.dimensions,
        "embedding_profile": profile,
        "chunking": options,
        "index_fingerprint": digest({"v": 1, "profile": profile, "chunking": options, "normalization": 1}),
    }


def validate_binding(metadata: dict[str, Any], binding: dict[str, str], profile: dict[str, Any]) -> None:
    if metadata.get("schema_version") != SCHEMA_VERSION or any(
        metadata.get(key) != value for key, value in binding.items()
    ):
        fail("Collection belongs to another source or schema", code="collection_incompatible", status=409)
    if metadata.get("embedding_profile") != profile:
        fail(
            "Embedding configuration changed; use the collection's original model/profile",
            code="collection_incompatible",
            status=409,
        )


def ensure_collection(qdrant: QdrantClient, collection: str, desired: dict[str, Any]) -> dict[str, Any]:
    if not qdrant.collection_exists(collection):
        try:
            qdrant.create_collection(
                collection_name=collection,
                vectors_config=VectorParams(size=desired["dimensions"], distance=Distance.COSINE),
            )
        except Exception:  # noqa: BLE001 -- possible concurrent creator; validate rather than adopt blindly
            if not qdrant.collection_exists(collection):
                fail("Cannot create collection", code="index_unavailable", status=502)
        else:
            desired = {**desired, "index_generation": str(uuid4()), "created_at": datetime.now(UTC).isoformat()}
            qdrant.upsert(
                collection_name=collection,
                points=[PointStruct(id=0, vector=[0.0] * desired["dimensions"], payload=desired)],
                wait=True,
            )
    stored = read_metadata(qdrant, collection)
    for key in (
        "schema_version",
        "source_id",
        "server_fingerprint",
        "library_id",
        "embedding_profile",
        "index_fingerprint",
    ):
        if stored.get(key) != desired.get(key):
            fail(
                "Collection source/model/index settings differ; choose a new collection",
                code="collection_incompatible",
                status=409,
            )
    params = qdrant.get_collection(collection).config.params.vectors
    if (
        not isinstance(params, VectorParams)
        or params.size != desired["dimensions"]
        or params.distance != Distance.COSINE
    ):
        fail("Collection vector settings are incompatible", code="collection_incompatible", status=409)
    if not isinstance(stored.get("index_generation"), str):
        fail("Collection generation is missing", code="collection_incompatible", status=409)
    return stored


def collection_name(source_id: str, library_id: str, model: str, fingerprint: str) -> str:
    label = re.sub(r"[^a-z0-9_-]+", "_", f"{source_id}_{library_id}_{model}".lower()).strip("_")
    return f"{label[:70]}_{fingerprint[:12]}"


def point_id(metadata: dict[str, Any], song_id: str, lyrics_hash: str, position: int) -> str:
    identity = [
        "section-v1",
        metadata["source_id"],
        metadata["library_id"],
        song_id,
        metadata["index_generation"],
        metadata["index_fingerprint"],
        lyrics_hash,
        position,
    ]
    return str(uuid5(POINT_NAMESPACE, canonical(identity)))


def lyric_hash(track: Track) -> str:
    return digest(
        {
            "v": 1,
            "language": track.language,
            "offset_ms": float(track.offset_ms),
            "lines": [[float(line.timestamp_sec), line.text] for line in track.lines],
        }
    )


def track_points(
    metadata: dict[str, Any], track: Track, chunks: list[LrcChunk], content_hash: str
) -> list[dict[str, Any]]:
    if len(chunks) > MAX_SONG_SECTIONS:
        fail("Song exceeds the section limit", code="section_limit", status=422)
    common = {
        "kind": "section",
        "schema_version": SCHEMA_VERSION,
        "source_id": track.source_id,
        "library_id": track.library_id,
        "song_id": track.song_id,
        "artist": track.artist,
        "title": track.title,
        "album": track.album,
        "lyrics_source": "navidrome",
        "lyrics_hash": content_hash,
        "index_fingerprint": metadata["index_fingerprint"],
        "index_generation": metadata["index_generation"],
        "indexed_at": datetime.now(UTC).isoformat(),
        "language": track.language,
    }
    return [
        {
            "id": point_id(metadata, track.song_id, content_hash, chunk.position),
            "payload": {
                **common,
                "section": chunk.section_name,
                "position": chunk.position,
                "total_sections": chunk.total_chunks,
                "lyrics": chunk.lyrics,
                "section_text_hash": digest(chunk.lyrics),
                "start_sec": chunk.start_sec,
                "duration_sec": chunk.duration_sec,
            },
        }
        for chunk in chunks
    ]


def section_filter(metadata: dict[str, Any], song_id: str | None = None) -> Filter:
    fields = {"kind": "section", "source_id": metadata["source_id"], "library_id": metadata["library_id"]}
    if song_id is not None:
        fields["song_id"] = song_id
    return Filter(must=[FieldCondition(key=key, match=MatchValue(value=value)) for key, value in fields.items()])


@dataclass
class SongState:
    """A derived section-set state, never a ledger or an optimistic completion flag."""

    complete: bool
    coherent: bool
    lyrics_hash: str | None
    records: list[Any] = field(repr=False)


def song_state(qdrant: QdrantClient, collection: str, metadata: dict[str, Any], song_id: str) -> SongState:
    records = []
    offset = None
    while True:
        page, offset = qdrant.scroll(
            collection_name=collection,
            scroll_filter=section_filter(metadata, song_id),
            limit=256,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        records.extend(page)
        if len(records) > MAX_SONG_SECTIONS:
            return SongState(complete=False, coherent=False, lyrics_hash=None, records=records)
        if offset is None:
            break
    if not records:
        return SongState(complete=False, coherent=True, lyrics_hash=None, records=[])
    try:
        first = records[0].payload
        count = first["total_sections"]
        content_hash = first["lyrics_hash"]
        positions = [record.payload["position"] for record in records]
        coherent = (
            type(count) is int
            and 0 < count <= MAX_SONG_SECTIONS
            and isinstance(content_hash, str)
            and len(set(positions)) == len(positions)
            and all(type(position) is int and 0 <= position < count for position in positions)
            and all(
                record.payload["total_sections"] == count
                and record.payload["lyrics_hash"] == content_hash
                and record.payload["index_fingerprint"] == metadata["index_fingerprint"]
                and record.payload["index_generation"] == metadata["index_generation"]
                and record.payload["schema_version"] == SCHEMA_VERSION
                and str(record.id) == point_id(metadata, song_id, content_hash, record.payload["position"])
                and isinstance(record.payload["lyrics"], str)
                and bool(record.payload["lyrics"].strip())
                and record.payload["section_text_hash"] == digest(record.payload["lyrics"])
                for record in records
            )
        )
        return SongState(coherent and len(records) == count, coherent, content_hash, records)
    except KeyError, TypeError, ValueError:
        return SongState(complete=False, coherent=False, lyrics_hash=None, records=records)
