"""Single-process background jobs adapting the shared ingestion operation."""

import logging
import secrets
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import suppress
from dataclasses import asdict, dataclass, field
from typing import Any

from qdrant_client import QdrantClient

from resonance import embedders
from resonance.application.ingest import IngestProgress, IngestResult, run_ingest
from resonance.config import Settings
from resonance.errors import ApplicationError, fail
from resonance.navidrome import NavidromeClient, NavidromeCredentials

ACTIVE_STATES = {"queued", "running", "stopping"}
RETRYABLE_ERRORS = {"dependency_unavailable", "navidrome_unavailable", "embedding_unavailable"}
MAX_RETAINED_JOBS = 50
logger = logging.getLogger("uvicorn.error.resonance.ingest_jobs")


@dataclass
class _Job:
    id: str
    owner: str
    request: dict[str, Any]
    state: str = "queued"
    progress: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    cancel: threading.Event = field(default_factory=threading.Event, repr=False)
    last_logged_tracks: int = 0
    last_progress_log: float = field(default_factory=time.monotonic)


class IngestJobManager:
    """Own one ingestion worker and an ephemeral, bounded status history."""

    def __init__(self, qdrant: QdrantClient, settings: Settings) -> None:
        self._qdrant = qdrant
        self._settings = settings
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="resonance-ingest")
        self._jobs: dict[str, _Job] = {}
        self._future: Future[None] | None = None
        self._lock = threading.RLock()
        self._closing = False

    def start(self, owner: str, body: dict[str, Any], session: Any) -> dict[str, Any]:
        with self._lock:
            self._ensure_idle()
            job = _Job(id=secrets.token_urlsafe(18), owner=owner, request=dict(body))
            self._jobs[job.id] = job
            self._trim()
            self._future = self._executor.submit(self._run, job, session.username, session.password)
            return self._serialize(job)

    def list(self, owner: str) -> list[dict[str, Any]]:
        with self._lock:
            return [self._serialize(job) for job in reversed(list(self._jobs.values())) if job.owner == owner]

    def is_collection_active(self, collection: str) -> bool:
        """Return whether an active job is using a known collection name."""
        with self._lock:
            return any(
                job.state in ACTIVE_STATES
                and (job.request.get("collection") == collection or job.progress.get("collection") == collection)
                for job in self._jobs.values()
            )

    def get(self, job_id: str, owner: str) -> dict[str, Any]:
        with self._lock:
            return self._serialize(self._owned(job_id, owner))

    def stop(self, job_id: str, owner: str) -> dict[str, Any]:
        with self._lock:
            job = self._owned(job_id, owner)
            if job.state in ACTIVE_STATES:
                job.state = "stopping"
                job.cancel.set()
                self._touch(job)
            return self._serialize(job)

    def resume(self, job_id: str, owner: str, session: Any) -> dict[str, Any]:
        with self._lock:
            job = self._owned(job_id, owner)
            if job.state not in {"stopped", "failed"} or (job.error_code and job.error_code not in RETRYABLE_ERRORS):
                fail("This ingestion job cannot be resumed", code="job_not_resumable", status=409)
            self._ensure_idle()
            job.state = "queued"
            job.error_code = None
            job.error_message = None
            job.progress = {}
            job.result = None
            job.cancel = threading.Event()
            job.updated_at = time.time()
            self._future = self._executor.submit(self._run, job, session.username, session.password)
            return self._serialize(job)

    def close(self) -> None:
        with self._lock:
            self._closing = True
            for job in self._jobs.values():
                if job.state in ACTIVE_STATES:
                    job.state = "stopping"
                    job.cancel.set()
            future = self._future
        if future is not None:
            future.result()
        self._executor.shutdown(wait=True, cancel_futures=False)

    def _run(self, job: _Job, username: str, password: str) -> None:
        with self._lock:
            if self._closing:
                job.state = "stopped"
                self._touch(job)
                return
            job.state = "running"
            self._touch(job)
        source: NavidromeClient | None = None
        stage = "Navidrome client setup"
        profile_id = job.request["profile"] or self._settings.embedding.profile
        try:
            source = NavidromeClient(self._settings.navidrome, NavidromeCredentials(username, password))
            stage = "embedding profile setup"
            embedder = embedders.resolve_embedder(profile_id, self._settings.embedding)
            stage = "library ingestion"
            logger.info(
                "Ingestion job started: id=%s library_id=%s profile=%s track_limit=%s custom_collection=%s",
                job.id,
                job.request["library_id"],
                profile_id,
                job.request.get("max_tracks") or "unlimited",
                bool(job.request.get("collection")),
            )
            result = run_ingest(
                qdrant=self._qdrant,
                embedder=embedder,
                settings=self._settings,
                source=source,
                library_id=job.request["library_id"],
                config_name=profile_id,
                collection=job.request.get("collection"),
                batch_size=job.request["batch_size"],
                gap_threshold_sec=job.request.get("gap_threshold_sec"),
                min_chunk_lines=job.request.get("min_chunk_lines"),
                max_tracks=job.request.get("max_tracks"),
                progress=lambda value: self._progress(job, value),
                should_stop=job.cancel.is_set,
            )
            self._finish_result(job, result)
        except ApplicationError as error:
            self._finish_error(job, error.code, str(error), stage, error.diagnostic)
        except Exception as error:  # noqa: BLE001 -- never expose provider exception contents
            logger.warning(
                "Ingestion job failed unexpectedly: id=%s stage=%s exception_type=%s",
                job.id,
                stage,
                type(error).__name__,
            )
            self._finish_error(
                job,
                "dependency_unavailable",
                "An unexpected ingestion error occurred. Check the Resonance container logs for its error type.",
                stage,
            )
        finally:
            if source is not None:
                with suppress(Exception):
                    source.close()

    def _progress(self, job: _Job, value: IngestProgress) -> None:
        with self._lock:
            job.progress = asdict(value)
            self._touch(job)
            now = time.monotonic()
            if value.tracks_seen - job.last_logged_tracks >= 100 or now - job.last_progress_log >= 30:
                job.last_logged_tracks = value.tracks_seen
                job.last_progress_log = now
                logger.info(
                    "Ingestion progress: id=%s collection=%s discovered=%d processed=%d unchanged=%d "
                    "skipped=%d sections=%d missing_lyrics=%d unsynced_lyrics=%d invalid_lyrics=%d",
                    job.id,
                    value.collection,
                    value.tracks_seen,
                    value.tracks_processed,
                    value.tracks_unchanged,
                    value.skipped,
                    value.sections_written,
                    value.missing_lyrics,
                    value.unsynced_lyrics,
                    value.invalid_lyrics,
                )

    def _finish_result(self, job: _Job, result: IngestResult) -> None:
        with self._lock:
            job.result = asdict(result)
            job.state = "stopped" if result.cancelled else "completed"
            self._touch(job)
        logger.info(
            "Ingestion job %s: id=%s collection=%s discovered=%d processed=%d unchanged=%d skipped=%d "
            "sections=%d missing_lyrics=%d unsynced_lyrics=%d invalid_lyrics=%d",
            job.state,
            job.id,
            result.collection,
            result.tracks_seen,
            result.tracks_processed,
            result.tracks_unchanged,
            result.skipped,
            result.sections_written,
            result.missing_lyrics,
            result.unsynced_lyrics,
            result.invalid_lyrics,
        )

    def _finish_error(self, job: _Job, code: str, message: str, stage: str, diagnostic: str | None = None) -> None:
        messages = {
            "refresh_required": "Track content changed; use a new collection until refresh is supported.",
            "collection_incompatible": "The selected collection is incompatible with this request.",
            "scope_mismatch": "The source returned a track outside the selected library.",
            "navidrome_unavailable": "Navidrome could not complete the ingestion request.",
            "embedding_unavailable": "The embedding service could not complete the request.",
            "invalid_configuration": (
                "Embedding profile or endpoint configuration is invalid; check the selected profile and served model."
            ),
            "invalid_embeddings": (
                "The embedding service returned vectors with an unexpected count or dimension; "
                "check the profile/model match."
            ),
            "index_unavailable": "Qdrant could not complete or verify an index operation.",
            "index_incomplete": "Qdrant did not confirm that all sections were written for a track.",
            "library_unavailable": "The selected Navidrome library is unavailable to this account.",
            "navidrome_protocol": "Navidrome returned an invalid response during ingestion.",
            "navidrome_rejected": "Navidrome rejected an ingestion request; check this account's library access.",
            "dependency_unavailable": "An ingestion dependency could not complete the request.",
        }
        safe_message = messages.get(code, message)
        with self._lock:
            job.state = "failed"
            job.error_code = code
            job.error_message = safe_message
            self._touch(job)
            progress = job.progress
        logger.error(
            "Ingestion job failed: id=%s stage=%s library_id=%s profile=%s collection=%s "
            "code=%s diagnostic=%s discovered=%d processed=%d unchanged=%d skipped=%d sections=%d "
            "missing_lyrics=%d unsynced_lyrics=%d invalid_lyrics=%d message=%s",
            job.id,
            stage,
            job.request["library_id"],
            job.request["profile"] or self._settings.embedding.profile,
            progress.get("collection") or job.request.get("collection") or "generated",
            code,
            diagnostic or "none",
            progress.get("tracks_seen", 0),
            progress.get("tracks_processed", 0),
            progress.get("tracks_unchanged", 0),
            progress.get("skipped", 0),
            progress.get("sections_written", 0),
            progress.get("missing_lyrics", 0),
            progress.get("unsynced_lyrics", 0),
            progress.get("invalid_lyrics", 0),
            safe_message,
        )

    def _ensure_idle(self) -> None:
        if self._closing:
            fail("Ingestion jobs are shutting down", code="jobs_unavailable", status=503)
        if any(job.state in ACTIVE_STATES for job in self._jobs.values()):
            fail("An ingestion job is already active", code="job_active", status=409)

    def _owned(self, job_id: str, owner: str) -> _Job:
        job = self._jobs.get(job_id)
        if job is None or job.owner != owner:
            fail("Ingestion job was not found", code="job_not_found", status=404)
        return job

    @staticmethod
    def _touch(job: _Job) -> None:
        job.updated_at = time.time()

    def _trim(self) -> None:
        terminal = [job_id for job_id, job in self._jobs.items() if job.state not in ACTIVE_STATES]
        while len(self._jobs) > MAX_RETAINED_JOBS and terminal:
            self._jobs.pop(terminal.pop(0), None)

    @staticmethod
    def _serialize(job: _Job) -> dict[str, Any]:
        return {
            "id": job.id,
            "state": job.state,
            "request": job.request,
            "progress": job.progress,
            "result": job.result,
            "error_code": job.error_code,
            "error_message": job.error_message,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
            "can_resume": job.state == "stopped" or (job.state == "failed" and job.error_code in RETRYABLE_ERRORS),
        }
