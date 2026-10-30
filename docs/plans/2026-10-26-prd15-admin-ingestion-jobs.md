---
status: completed
approved: true
iterations: 0
branch: spec/prd15-ingestion-jobs
base_branch: main
base_commit: 1e51867
prd: docs/prds/15-admin-ingestion-jobs.md
created: 2026-10-26
updated: 2026-10-26
author: MK
tags: [admin, ingestion, jobs, qdrant, vue]
---

# PRD-15 Admin Ingestion Jobs Implementation Plan

## Summary

**Goal:** Give admins progress, safe stop, and explicit resume controls for long
Navidrome-to-Qdrant ingestion runs.
**Architecture:** Add transport-independent progress/stop callbacks to the existing
ingest operation, run it in a single-worker in-process manager, and expose admin-only
job controls over FastAPI. Keep job status ephemeral; Qdrant remains the durable record
of completed section writes and is the basis for resume.
**Tech Stack:** Python threads, FastAPI, existing application ingestion, Qdrant, Vue 3.

## Scope

### In Scope

- Live counters and states for one active ingestion job at a time.
- Cooperative stop at track/embedding-batch boundaries.
- Explicit resume with the same stored request after a stopped or retryable failed job.
- Admin-only start/list/status/stop/resume endpoints.
- Vue admin controls and status display, using the existing create-and-ingest form.
- Graceful worker stop before Qdrant/embedder shutdown.

### Out of Scope

- Durable job history/checkpoints, SQLite job state, multiple workers/processes, or
  simultaneous ingestion jobs.
- Incremental reconciliation of changed/deleted tracks, scheduled refresh, or automatic
  re-embedding. Keep current `refresh_required` behavior.
- Arbitrary pause inside a provider/network call or Qdrant batch.
- Job recovery after service restart. The admin can resubmit the same collection request;
  safe point IDs and Qdrant-derived completion state resume unchanged/partial work.
- Changes to synchronous `POST /api/ingest` for CLI/API compatibility.

## Prerequisites

- Admin collection setup is merged on `main` (`cc34d69` and later tracker commit).
- `application.run_ingest` uses deterministic section IDs and can skip complete sections
  or finish identical partial writes.
- Single-process/single-worker FastAPI assumption remains true because auth sessions are
  process-local.

## Context for Implementer

- **Patterns:** `src/resonance/application/ingest.py` owns the track loop and Qdrant write
  boundaries; `src/resonance/routes/ingest.py` is the thin authenticated HTTP adapter;
  `src/resonance/app.py` owns Qdrant and embedder lifecycle; `vue-ui/src/App.vue` owns
  the admin collection card.
- **Conventions:** Admin authorization is enforced by `require_admin` on every endpoint.
  Errors are safe `ApplicationError`s; do not expose raw provider responses, credentials,
  lyrics, or tracebacks in job responses.
- **Key files:** `src/resonance/application/ingest.py`, new
  `src/resonance/application/ingest_jobs.py`, `src/resonance/routes/ingest.py`,
  `src/resonance/app.py`, `src/resonance/routes/auth.py`, `vue-ui/src/App.vue`,
  `vue-ui/src/style.css`, `README.md`, PRD-09 and PRD-15.
- **Gotchas:** `get_navidrome` closes its request-scoped client after the response; a
  background worker must create and close its own client from the authenticated session.
  Do not retain password in a job record. Shutdown must request stop and join workers
  before closing shared Qdrant/embedder dependencies.
- **Domain context:** Navidrome enumeration has no reliable total, so report observed
  counters rather than a misleading percent. Stop is cooperative: finish an active
  external call and Qdrant upsert batch, then stop. Resume uses the exact original
  request and existing Qdrant song-state checks. Changed lyrics remain a terminal
  `refresh_required` error requiring a new collection.
- **Artifact directory:** `/tmp/resonance-prd15-ingestion-artifacts`
- **Test framework constraints:** Repository has pytest/TestClient and mocked external
  clients, but do not add or run tests in this implementation pass. Use source review,
  type/lint checks, and Vite production build; live Navidrome/Qdrant acceptance remains
  for operator validation.

## Runtime Environment

- **Start command:** `make run`, plus `make ui` for Vite development.
- **Ports:** FastAPI `127.0.0.1:8000`; Vite `127.0.0.1:5173`.
- **Deploy path:** Existing image serves the compiled Vue app under `/app/`.
- **Health check:** `GET /health`, requiring reachable Qdrant.
- **Restart procedure:** Restart API and Vite as needed; production use `make prod`.
- **Code identity:** Run this worktree or rebuild the image and verify the new job routes
  and Vue bundle come from this branch.

## Feature Inventory

| Existing behavior                                                 | Function/route                    | Destination                                                | Task      |
| ----------------------------------------------------------------- | --------------------------------- | ---------------------------------------------------------- | --------- |
| Synchronous API ingestion returns one final summary               | `POST /api/ingest` → `run_ingest` | Retained for CLI and direct callers                        | Tasks 1–2 |
| Additive/idempotent Qdrant writes with per-song completion checks | `run_ingest`/`song_state`         | Same logic, add callbacks at safe boundaries               | Task 1    |
| Vue admin creates collection and waits for full request           | `createCollection`                | Start/poll/stop/resume job; retain same fields and results | Task 3    |
| FastAPI owns Qdrant and embedder lifecycle                        | app lifespan                      | Stop/join job worker before resource close                 | Task 2    |

## Progress Tracking

- [x] Task 1: Add cooperative progress and cancellation checkpoints to shared ingestion.
- [x] Task 2: Add single-worker in-process job manager and admin job API.
- [x] Task 3: Wire Vue admin workflow to start, poll, stop, and resume jobs.
- [x] Task 4: Update docs and roadmap; live operator acceptance remains outstanding.

**Total Tasks:** 4 | **Completed:** 4 | **Remaining:** 0

## Implementation Tasks

### Task 1: Shared ingestion progress and cooperative stop

**Objective:** Make ingestion report safe progress snapshots and stop at explicit
checkpoints without changing the default CLI/synchronous behavior.

**Dependencies:** None

**Files:**

- Modify: `src/resonance/application/ingest.py`.
- No tests added or run.

**Key Decisions / Notes:**

- Add optional progress callback and stop predicate; keep default `None` behavior.
- Report immutable counters after track transitions and Qdrant batches.
- Check stop before processing a discovered track and before each embedding batch.
- If stop arrives during an embedding/Qdrant call, finish that batch and report
  cancellation at the next checkpoint. Leave existing partial-state validation intact.

**Definition of Done:**

- [x] Existing callers that omit callbacks retain their current behavior.
- [x] Callbacks expose counters but no titles, IDs, lyrics, or credentials.
- [x] Stop yields a clearly marked partial result and never deletes completed writes.

**Verify:**

- `ruff check src/`, `ruff format --check src/`, and `ty check src/` pass.
- Source trace confirms every stop point is outside a half-applied Qdrant batch.

### Task 2: Job manager and authenticated API

**Objective:** Run one ingestion job off-request and provide admin-only job controls.

**Dependencies:** Task 1

**Files:**

- Create: `src/resonance/application/ingest_jobs.py`.
- Modify: `src/resonance/routes/ingest.py`, `src/resonance/app.py`.
- No tests added or run.

**Key Decisions / Notes:**

- Use a process-local single-worker executor and bounded in-memory history; no SQLite,
  queue, or additional service.
- Add `POST /api/ingest-jobs`, `GET /api/ingest-jobs`, `GET /api/ingest-jobs/{id}`,
  `POST /api/ingest-jobs/{id}/stop`, and `POST /api/ingest-jobs/{id}/resume`.
- Job owner is the configured admin username. Every read/mutation requires admin and
  checks job ownership.
- Job request is immutable. Resume reuses its exact library/profile/collection/chunking/
  limit parameters and requires a fresh authenticated session to create a new source.
- Store only safe request fields and counters; never persist the session password.
- Refuse a second active job. Mark `refresh_required` and collection incompatibility as
  non-resumable; other failures are resumable only when safe to retry unchanged input.
- On shutdown, signal cooperative stop and wait for worker completion before application
  dependencies close.

**Definition of Done:**

- [x] Start returns immediately with an opaque job ID and active status.
- [x] List/status reflect current counters and terminal state.
- [x] Non-admin/unauthenticated callers cannot start, inspect, stop, or resume jobs.
- [x] One active job limit prevents overlapping writes.
- [x] Stop/resume and retryable failures use the original request; changed lyrics and
      incompatible collections are not auto-retried.
- [x] Shutdown requests stop before Qdrant/embedder close.

**Verify:**

- Static/source review for route dependencies, owner checks, credential handling, thread
  lifecycle, and state transitions.
- `ruff check src/`, `ruff format --check src/`, and `ty check src/` pass.

### Task 3: Vue progress and controls

**Objective:** Let the admin observe an active job, stop it safely, and explicitly resume
the same request.

**Dependencies:** Task 2

**Files:**

- Modify: `vue-ui/src/App.vue`, `vue-ui/src/style.css`.
- Verify: Vite build and operator browser acceptance.

**Key Decisions / Notes:**

- Replace the admin card's long-held `/api/ingest` request with start-job plus polling.
- Poll active jobs on admin page load so navigation/reload during a run can reconnect.
- Display discovered, processed, unchanged, skipped, section and lyric-skip counters;
  do not invent a percent-complete total.
- Disable collection creation while a job is active. Show stop confirmation and a
  stopping state until safe cancellation is acknowledged.
- Show Resume only for stopped or retryable failed jobs. Do not auto-resume after an
  unknown network result or service restart.
- On completion refresh `/api/collections`, select the result, and display summary.

**Definition of Done:**

- [x] Admin sees live progress from a started job and can reconnect after page reload.
- [x] Stop control reports stopping then stopped; no false claim of immediate kill.
- [x] Resume is explicit, uses the same request, and completion refreshes collection
      choices for search.
- [x] Errors and unavailable job IDs are visible without exposing secrets or lyric data.

**Verify:**

- `./node_modules/.bin/vite build` — production UI compiles.
- Operator acceptance with a bounded Navidrome library run: start, observe counters,
  stop, resume, and confirm a searchable collection.

### Task 4: Documentation and roadmap

**Objective:** Explain the admin job lifecycle, safe stop/resume semantics, and restart
limits, and record progress under v1 pillar 1.

**Dependencies:** Tasks 1–3

**Files:**

- Modify: `README.md`, `docs/roadmap.md`, PRD-09 follow-on note, this plan.

**Definition of Done:**

- [x] Docs explain that stop is cooperative, restart loses job status, and rerunning the
      same collection resumes only unchanged/identical partial writes.
- [x] Roadmap distinguishes implementation from live acceptance and full refresh.
- [x] Plan records lint/type/build and the operator acceptance limitation.

**Verify:**

- `git diff --check` passes; commit hooks' formatting/type checks pass.

## Testing Strategy

- Source review covers API authorization, owner scoping, state transitions, and resource
  shutdown ordering.
- Lint/type checks and Vite production build cover static correctness.
- Authenticated live Navidrome/Qdrant operation is left to the operator; do not claim it
  passed based on a source review.
- No automated tests are added or run in this pass.

## Implementation Evidence

- Ruff lint and format checks passed for changed Python modules.
- `ty check src/resonance` passed.
- `git diff --check` passed.
- Vite production build passed using the existing local dependency install; the temporary
  `node_modules` link was removed afterward.
- No tests or live service operations were run. Manual behavior review was performed by
  the implementer; no independent reviewer approval is claimed.
- Remaining acceptance: operator must start a bounded UI job, observe progress, stop,
  resume, and confirm the collection can be searched against the live Navidrome/Qdrant.

## Risks and Mitigations

| Risk                                            | Likelihood | Impact | Concrete mitigation                                                                       |
| ----------------------------------------------- | ---------- | ------ | ----------------------------------------------------------------------------------------- |
| Stop requested during vector write              | Med        | High   | Check stop between batches and acknowledge only after current batch completes.            |
| Duplicate start overlaps same collection        | Med        | High   | Single-worker manager rejects starts while any job is active.                             |
| App shutdown closes Qdrant while worker uses it | Low        | High   | Signal stop and join manager worker before closing Qdrant/embedder clients.               |
| Browser loses job ID                            | Med        | Med    | List active jobs on page refresh; retain bounded in-memory job list for process lifetime. |
| Service restart clears job status               | Med        | Med    | Document that Qdrant writes persist and same collection can be resubmitted to resume.     |
| Changed lyric state is mistaken for resumable   | Low        | High   | Keep `refresh_required` terminal and exclude it from resume eligibility.                  |

## Removes

- None. Keep synchronous `POST /api/ingest` for CLI and direct API compatibility.

### Removes (verify)

- None.

## ADR Reference

No ADR needed. This adds an in-process adapter around the existing shared ingestion
operation and does not alter collection schema or indexing policy.

## Open Questions

- None for this bounded, single-worker job lifecycle.

### Deferred Ideas

- Persistent job ledger, distributed workers, concurrent library ingestion, and
  changed/deleted-track refresh.
- Real MCP user tools and PRD-10 open-source readiness.
