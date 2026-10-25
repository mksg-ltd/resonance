"""Caller-scoped Qdrant collection discovery."""

from dataclasses import dataclass
from typing import Any

from qdrant_client import QdrantClient

from resonance.application.indexing import migrate_legacy_metadata, read_metadata
from resonance.errors import ApplicationError, fail


@dataclass(frozen=True)
class VisibleCollection:
    name: str
    points_count: int
    metadata: dict[str, Any]


def visible_collections(
    qdrant: QdrantClient,
    binding: dict[str, str],
    allowed_library_ids: set[str],
    *,
    legacy_fingerprint: str | None = None,
) -> list[VisibleCollection]:
    """Return collections bound to this server and the caller's current libraries."""
    try:
        names = qdrant.get_collections().collections
    except Exception:  # noqa: BLE001 -- Qdrant SDK boundary
        fail("Cannot list indexed collections", code="index_unavailable", status=502)
    visible = []
    for collection in names:
        try:
            info = qdrant.get_collection(collection.name)
            if not info.points_count:
                continue
            metadata = read_metadata(qdrant, collection.name)
        except ApplicationError as error:
            if error.code == "collection_incompatible":
                continue
            raise
        if metadata.get("source_id") != binding.get("source_id"):
            continue
        library_id = metadata.get("library_id")
        if not isinstance(library_id, str) or library_id not in allowed_library_ids:
            continue
        if metadata.get("server_fingerprint") != binding.get("server_fingerprint"):
            if legacy_fingerprint is None:
                continue
            try:
                metadata = migrate_legacy_metadata(
                    qdrant,
                    collection.name,
                    {**metadata, **binding},
                    legacy_fingerprint,
                )
            except ApplicationError as error:
                if error.code == "collection_incompatible":
                    continue
                raise
        visible.append(VisibleCollection(collection.name, info.points_count or 0, metadata))
    return sorted(visible, key=lambda item: item.name)
