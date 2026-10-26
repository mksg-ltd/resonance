"""Thin HTTP adapter for Navidrome-native library ingestion."""

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from resonance import embedders
from resonance.application.ingest import run_ingest
from resonance.application.ingest_jobs import IngestJobManager
from resonance.auth import Principal, UserSession
from resonance.errors import fail
from resonance.navidrome import NavidromeClient
from resonance.routes.auth import get_navidrome, get_user_session, require_admin

router = APIRouter(prefix="/api")


class IngestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile: str | None = Field(
        default=None,
        min_length=1,
        validation_alias=AliasChoices("profile", "provider"),
    )
    library_id: str = Field(min_length=1)
    collection: str | None = Field(default=None, min_length=1, max_length=255)
    batch_size: int = Field(default=32, ge=1, le=2048)
    gap_threshold_sec: float | None = Field(default=None, gt=0)
    min_chunk_lines: int | None = Field(default=None, ge=1)
    max_tracks: int | None = Field(default=None, ge=1)


@router.post("/ingest", dependencies=[Depends(require_admin)])
def ingest(body: IngestRequest, request: Request, source: Annotated[NavidromeClient, Depends(get_navidrome)]) -> dict:
    profile_id = body.profile or request.app.state.settings.embedding.profile
    result = run_ingest(
        qdrant=request.app.state.qdrant,
        embedder=embedders.resolve_embedder(profile_id, request.app.state.settings.embedding),
        settings=request.app.state.settings,
        source=source,
        library_id=body.library_id,
        config_name=profile_id,
        collection=body.collection,
        batch_size=body.batch_size,
        gap_threshold_sec=body.gap_threshold_sec,
        min_chunk_lines=body.min_chunk_lines,
        max_tracks=body.max_tracks,
    )
    return asdict(result)


def _job_manager(request: Request) -> IngestJobManager:
    manager = getattr(request.app.state, "ingest_jobs", None)
    if manager is None:
        fail("Ingestion jobs are unavailable", code="jobs_unavailable", status=503)
    return manager


@router.post("/ingest-jobs", status_code=202)
def start_ingest_job(
    body: IngestRequest,
    request: Request,
    principal: Annotated[Principal, Depends(require_admin)],
    session: Annotated[UserSession, Depends(get_user_session)],
) -> dict:
    return _job_manager(request).start(principal.username, body.model_dump(), session)


@router.get("/ingest-jobs")
def list_ingest_jobs(request: Request, principal: Annotated[Principal, Depends(require_admin)]) -> dict:
    return {"jobs": _job_manager(request).list(principal.username)}


@router.get("/ingest-jobs/{job_id}")
def get_ingest_job(job_id: str, request: Request, principal: Annotated[Principal, Depends(require_admin)]) -> dict:
    return _job_manager(request).get(job_id, principal.username)


@router.post("/ingest-jobs/{job_id}/stop")
def stop_ingest_job(job_id: str, request: Request, principal: Annotated[Principal, Depends(require_admin)]) -> dict:
    return _job_manager(request).stop(job_id, principal.username)


@router.post("/ingest-jobs/{job_id}/resume", status_code=202)
def resume_ingest_job(
    job_id: str,
    request: Request,
    principal: Annotated[Principal, Depends(require_admin)],
    session: Annotated[UserSession, Depends(get_user_session)],
) -> dict:
    return _job_manager(request).resume(job_id, principal.username, session)
