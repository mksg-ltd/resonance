"""Thin HTTP adapter for Navidrome-native library ingestion."""

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from resonance import embedders
from resonance.application.ingest import run_ingest
from resonance.navidrome import NavidromeClient
from resonance.routes.auth import get_navidrome, require_operator

router = APIRouter(prefix="/api")


class IngestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1)
    library_id: str = Field(min_length=1)
    collection: str | None = Field(default=None, min_length=1, max_length=255)
    batch_size: int = Field(default=32, ge=1, le=2048)
    gap_threshold_sec: float | None = Field(default=None, gt=0)
    min_chunk_lines: int | None = Field(default=None, ge=1)
    max_tracks: int | None = Field(default=None, ge=1)


@router.post("/ingest", dependencies=[Depends(require_operator)])
def ingest(body: IngestRequest, request: Request, source: Annotated[NavidromeClient, Depends(get_navidrome)]) -> dict:
    result = run_ingest(
        qdrant=request.app.state.qdrant,
        embedder=embedders.resolve_embedder(body.provider),
        settings=request.app.state.settings,
        source=source,
        library_id=body.library_id,
        config_name=body.provider,
        collection=body.collection,
        batch_size=body.batch_size,
        gap_threshold_sec=body.gap_threshold_sec,
        min_chunk_lines=body.min_chunk_lines,
        max_tracks=body.max_tracks,
    )
    return asdict(result)
