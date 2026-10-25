"""Collections endpoint — list and manage Qdrant collections."""

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api")


class CollectionInfo(BaseModel):
    """Collection summary."""

    name: str
    points_count: int
    provider: str | None = None
    model: str | None = None
    dimensions: int | None = None
    source_id: str | None = None
    library_id: str | None = None
    index_fingerprint: str | None = None


@router.get("/collections", response_model=list[CollectionInfo])
def list_collections(request: Request) -> list[CollectionInfo]:
    """List all Qdrant collections with their metadata."""
    qdrant = request.app.state.qdrant
    collections = qdrant.get_collections().collections

    result = []
    for col in collections:
        info = qdrant.get_collection(col.name)
        points_count = info.points_count or 0

        # Try to read collection metadata from point id=0
        provider = None
        model = None
        dimensions = None
        binding = {}
        if points_count > 0:
            try:
                points = qdrant.retrieve(collection_name=col.name, ids=[0])
                if points and points[0].payload and points[0].payload.get("_metadata"):
                    payload = points[0].payload
                    provider = payload.get("provider")
                    model = payload.get("model")
                    dimensions = payload.get("dimensions")
                    binding = {key: payload.get(key) for key in ("source_id", "library_id", "index_fingerprint")}
            except Exception:  # noqa: BLE001
                pass

        result.append(
            CollectionInfo(
                name=col.name,
                points_count=points_count,
                provider=provider,
                model=model,
                dimensions=dimensions,
                **binding,
            )
        )

    return result


@router.delete("/collections/{name}")
def delete_collection(name: str, request: Request) -> dict:
    """Drop a Qdrant collection."""
    qdrant = request.app.state.qdrant
    qdrant.delete_collection(name)
    return {"deleted": name}
