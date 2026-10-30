---
status: completed
author: MK
tags:
  [
    admin,
    ingestion,
    progress,
    cancellation,
    qdrant,
    implemented,
    operator-acceptance-pending,
  ]
title: "PRD-15: Admin Ingestion Jobs"
phase: implementation
created: 2026-10-26
updated: 2026-10-27
---

# PRD-15: Admin Ingestion Jobs

**Status**: Implemented in `main` (`b84b2ba`). Live operator acceptance of progress,
safe stop, resume, and a searchable resulting collection remains outstanding.

## Purpose

Let the configured Resonance admin monitor long collection ingestions, stop them at a
safe checkpoint, and resume the same request without losing completed Qdrant writes.
This closes a known operator usability gap before v1 without changing who may ingest or
how searchable collections are identified.

## Problem

`POST /api/ingest` runs synchronously for the entire selected library or requested
track limit. The browser cannot show progress, and a lost connection leaves the admin
unsure whether work continues. Navidrome enumeration, lyrics retrieval, embedding, and
Qdrant writes can take long enough for browser/proxy timeouts.

The ingestion operation already uses deterministic point IDs, verifies complete
per-song section sets, skips unchanged songs, and can finish identical partial writes.
The HTTP interface does not yet expose those checkpoints as a controllable operation.

## Goals

- Run ingestion as a background job while keeping all indexing policy in
  `application.run_ingest`.
- Expose admin-only start, list/status, stop, and resume actions through FastAPI.
- Report live counters: tracks discovered, processed, unchanged, skipped, sections
  written, missing/unsynced lyrics, collection, and current state.
- Stop cooperatively between safe work units; complete any active external call and
  Qdrant upsert batch before acknowledging the stopped state.
- Resume a stopped or retryable failed job with its exact immutable request. Existing
  Qdrant section state determines what is complete; no completed writes are rolled back.
- Connect the Vue admin form to job polling, stop, and resume controls.
- Keep the setup self-contained: one Resonance process, no Celery/Redis service, no
  service credential, and no job metadata database.

## Non-Goals

- Changed-lyric replacement, deleted-track pruning, scheduled or webhook refresh, or
  any change to the current `refresh_required` policy.
- Multiple simultaneous ingestion jobs, distributed workers, multi-process job
  orchestration, durable audit history, or recovery of job UI state after service restart.
- A percent-complete estimate when Navidrome's paged track enumeration has no reliable
  total. The UI may show discovered/processed counts and an indeterminate progress state.
- Pause at an arbitrary point inside a provider call, vector upsert, or track. Stop is
  cooperative at checkpoints.
- Embedding endpoint settings UI or ordinary-user access to ingestion.

## User Flow

1. An admin chooses an authorized Navidrome library, profile, optional collection name,
   and optional track limit in Vue.
2. Vue starts a job and receives its opaque job ID promptly.
3. Vue polls the job status and displays live counters and the current phase.
4. Stop requests cancellation. The job finishes its in-flight safe work unit and then
   reports `stopped`.
5. The admin resumes the stopped job. It reruns the same immutable request against the
   same collection; Qdrant completion state skips complete songs and resumes identical
   partial section writes.
6. A terminal error is reported with a safe error code/message. `refresh_required` is
   not auto-retried: the admin starts a new collection for changed lyrics.

If Resonance restarts, in-memory job status is lost. The Qdrant writes remain. The admin
can submit the same collection/profile/library request again after signing in; this
starts a new job that relies on the existing safe additive-resume behavior.

## Architecture

- Add optional progress and stop callbacks to `application.run_ingest`; default
  callbacks preserve CLI behavior. Invoke callbacks only at safe boundaries and report
  counter snapshots without lyric text, song titles, credentials, or provider payloads.
- Add a process-local `IngestJobManager` owned by the FastAPI app lifespan. It keeps
  immutable sanitized requests, status/counters/timestamps, and a cancellation event.
  Permit one active ingestion job at a time in this single-process v1.
- Start worker work in a thread so the API can return immediately. The worker creates
  and closes its own Navidrome client from the authenticated admin session credentials;
  credentials are not stored on the job object.
- Job IDs are random and scoped to the configured admin principal. Expose no password,
  cookie, bearer token, lyrics, or raw external exception text in job responses/logs.
- Job state is in memory; Qdrant remains authoritative for indexed section completion.
  Do not add SQLite job state or a second completion ledger.
- On application shutdown, request cooperative stop for active jobs and join workers
  before closing Qdrant or embedding clients.
- Reuse the existing Vue admin collection form; show job state and controls adjacent to
  the form and make completed collections selectable as today.

### Job States

`queued` → `running` → (`stopping` → `stopped`) or `completed` / `failed`.
`stopped` and retryable `failed` jobs may transition back to `queued` only through an
explicit resume request that reuses the exact stored request. Job output exposes a
safe `error_code`, not a traceback or raw provider response.

## Acceptance Criteria

- Admin starts ingestion and receives a job ID before whole-library processing ends.
- Job status returns current counters and state; polling never returns passwords,
  bearer/session tokens, lyric text, or raw external exception messages.
- A normal user and an unauthenticated caller cannot start, inspect, stop, or resume a
  job; denied requests do not create worker threads or touch Navidrome/Qdrant.
- Only one job runs at a time; a second start receives a conflict response and does not
  alter the active request.
- Stop during enumeration, lyrics fetch, embedding, or Qdrant write is acknowledged at
  the next safe checkpoint. Already completed vectors remain intact.
- Resuming a stopped identical job completes or skips its already-complete sections
  without duplicate points. Changing the request under a job ID is rejected.
- `refresh_required` and collection incompatibility remain terminal for that request;
  the job manager does not silently change collection or delete/recreate data.
- Service shutdown asks workers to stop before Qdrant/embedder cleanup. A subsequent
  startup can safely re-run the same collection request even though prior job status is
  no longer available.
- Vue displays active progress, stop state, terminal success/error, and an explicit
  resume action; no automatic retry is triggered after an uncertain or failed run.

## Risks and Mitigations

- **Stop races with writes:** poll cancellation before each track and before each
  embedding/upsert batch; report `stopped` only after the current batch boundary.
- **Duplicate concurrent writers:** manager allows one active job, and an active run
  cannot be resumed or replaced until it reaches a terminal state.
- **Request/UI disconnect:** job continues independently; Vue lists current process jobs
  on reconnect, and a post-restart rerun remains safe through Qdrant state.
- **Credential retention:** worker receives transient session credentials only to build
  its owned source client; job status/request persistence contains no credentials.
- **Misleading progress percentage:** do not emit a percentage unless a reliable total
  is available; show observed counters and indeterminate activity.
- **Incompatible data mistaken for resumable:** preserve application-layer fingerprint
  and `refresh_required` checks; present those errors without a “resume” action.

## Relationship to Other PRDs

- Extends the administrative follow-on row in [PRD-09](09-navidrome-semantic-playlists.md)
  that names ingestion progress/cancel/retry. It does not reopen PRD-09's completed
  backend/indexing scope.
- Completes the operational side of collection setup started in the
  [admin collection creation plan](../plans/2026-10-26-admin-collection-creation.md).
- Does not include user MCP tools (next separate pillar) or PRD-10 open-source readiness.

## Deferred Work

- Persistent job history/checkpoints, multi-worker orchestration, job scheduling,
  incremental refresh, and changed/deleted-track reconciliation.
- Shutdown recovery beyond explicitly resubmitting the same collection request.
