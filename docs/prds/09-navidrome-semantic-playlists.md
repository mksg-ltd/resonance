---
phase: proof-of-concept
status: draft
backend_status: search-and-ingest-implemented
backend_completed: 2026-10-25
updated: 2026-10-25
created: 2026-10-23
author: strand
tags: [playlists, navidrome, semantic-search, lyrics]
---

# Navidrome Semantic Playlists

**Status**: Active product direction — backend and local search/ingestion PoC implemented; user-facing generation/MCP scope is follow-on work

**Current delivery boundary**: Single-account Navidrome backend capabilities and a minimal local HTML proof of concept for an operator to ingest and search. The PoC is intentionally not the eventual user product. Ingestion and model/library configuration are administrative operations; semantic search and playlist creation are user-facing operations intended for assistant/MCP use. Vue, end-user authentication, and MCP are separate follow-on work.

**Reconciliation**: Navidrome discovery, ingestion, collection creation, semantic search, and private playlist save operations exist in shared application operations with CLI/FastAPI adapters. The local HTML PoC provides an operator workflow for choosing a library, creating a collection, ingesting, and searching. Its purpose is to test backend workflows, not to define the eventual end-user UI. The [architecture decision](../adr/001-navidrome-application-boundary.md) and [runtime validation record](../plans/2026-10-25-navidrome-validation.md) document existing contracts and evidence.

---

## Overview

Let a user index one selected Navidrome library and search its synced lyrics by meaning, using the existing API and a minimal local HTML client. Search similarity means **lyric meaning**, not sound, genre, tempo, or mood inferred from audio.

Navidrome is the only supported music server; Jellyfin is not a dependency or acceptance target. The earlier [Jellyfin plugin PRD](04-jellyfin-plugin.md) is superseded by this direction and remains historical context.

## Goals

- Provide a small local page to choose a visible Navidrome library, create/populate an index collection, and search it.
- Reuse the shared application operations so CLI, FastAPI, and future interfaces do not duplicate product logic.
- Use Navidrome as the source of track metadata, song identity, and available synced lyrics; do not require a mounted music library.
- Preserve current safe re-ingestion behavior: add newly discovered eligible tracks, skip unchanged complete tracks, and resume identical partial writes.
- Keep a clear path to a later Vue UI, FastMCP adapter, and semantic playlist workflow without requiring them for this PoC.

## Non-Goals

- Implementing the whole semantic-playlist product in one release.
- M3U export/import as a substitute for a server playlist.
- A Jellyfin plugin, multi-server synchronization, audio analysis, or streaming music
  discovery outside the user's library.
- Bundling a lyrics corpus, introducing a lyrics crawler, or promising relevance for
  tracks with no usable lyrics.
- A mandatory generative LLM or a claim that every semantic result is objectively correct.
- Building Vue or FastMCP now.
- Seed/theme playlist generation, automatic prompt interpretation, candidate preview/editing, or any playlist-creation UI.
- Playlist updates, public sharing, multi-user or multi-server support, scheduled ingestion, or full changed/deleted-track reconciliation.

## Current State and Remaining Work

The core backend work is already implemented and exercised. The cleanup in [PRD-11](11-embedding-profile-configuration.md) removed the obsolete scanner, raw-LRC tool, and local M3U route while preserving Navidrome operations and shared chunking.

| Capability                                 | Current state                                                                                                        | Remaining work in this PoC                                             |
| ------------------------------------------ | -------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| Navidrome account and library discovery    | Implemented through shared application operations and protected FastAPI routes                                       | Page selector is implemented; local acceptance remains                 |
| Synced lyric ingestion and Qdrant indexing | Implemented in CLI/API; creates a derived collection when omitted or uses a supplied collection name                 | Page form is implemented; local acceptance remains                     |
| New/unchanged track handling               | Re-running ingestion adds new eligible tracks, skips unchanged complete tracks, and resumes identical partial writes | Safe additive re-ingestion is implemented; it is not full refresh      |
| Semantic search                            | Implemented in application layer, CLI, API, and HTML for existing collections                                        | Page now connects ingestion output to search; local acceptance remains |
| Private Navidrome playlist save            | Implemented and runtime-validated through CLI/API                                                                    | No UI or generated playlist behavior in this milestone                 |
| Minimal browser UI                         | Static page searches collections and now has token/library/ingestion controls                                        | Run local acceptance against the user's services                       |

### Ingestion and Refresh Semantics

The existing ingestion operation creates a collection when `collection` is omitted; its generated name binds the configured server, library, model, and indexing fingerprint. A supplied collection name is only reused if its source/library/profile/index settings match. An ingestion run is safe to repeat for additions and identical retries: unchanged complete songs are skipped, newly visible usable songs are indexed, and identical partial writes can resume. `max_tracks` bounds a run and the result reports whether enumeration completed. The API request is synchronous and has no progress updates; the PoC should default to 10 tracks and explain that full-library runs may take a while. If a browser connection fails before receiving the result, a same-collection retry can safely skip unchanged complete sections and resume identical partial writes.

This is **not a full refresh**. When ingestion encounters already-indexed lyrics or section count that changed, the API returns `refresh_required` without replacing that song's stored sections. Earlier new songs fully processed in the same request remain indexed. Deleted or inaccessible songs are not pruned. The PoC must not imply otherwise or offer a destructive reset action. Full changed/deleted-track reconciliation remains a separate future design.

### Static UI Runtime

The page will be served separately as requested, for example with `python -m http.server 8080 --bind 127.0.0.1` from `ui/`, while the FastAPI development server runs at `http://localhost:8000`. Do not use the static server's default port 8000 because that is the API port. The PoC can keep the API URL as a fixed local constant in the page. The dev API must bind to loopback and allow only the local UI origins (`http://localhost:8080` and `http://127.0.0.1:8080`) through CORS. Library listing and ingestion require the operator bearer token; the page has one simple token field and keeps its value only in page memory, never embeds or fetches it from `.env`. The configured Navidrome credentials remain server-side.

The app also currently serves the same static directory at `/ui`; that same-origin path is an alternative for local use, but the PoC acceptance path is the user's separately served `ui/` directory.

### Live Navidrome Validation

On 2026-10-25, authentication succeeded against Navidrome **0.64.2 (10114574)**,
Subsonic **1.16.1**. It advertises form POST and `songLyrics` versions 1 and 2.
Paged listing returned **4,187 unique tracks** in the English library (`musicFolderId=2`).
Structured lyric retrieval succeeded for ten tracks sampled across that listing;
all ten returned synced lyrics. This is a sample, not a whole-library coverage guarantee.

An empty test playlist was created and its XML readback explicitly reported
`public="false"` before any tracks or visibility updates. Three tracks were then added
to that same test playlist; readback verified exact ID, owner, name, private visibility,
count, and order. The user confirmed seeing the playlist and all three entries in their
client. The user later confirmed audible playback and advancing through those tracks
in a browser. The exact browser/client version and the private indicator shown in that
client remain unrecorded.

Important compatibility finding: this version omits `public=false` from JSON.
Absence must not be interpreted as `true`; XML readback supplies an explicit boolean.
See the [version-pinned response definition](https://github.com/navidrome/navidrome/blob/v0.64.2/server/subsonic/responses/responses.go#L280)
and the [validation record](../plans/2026-10-25-navidrome-validation.md).

Assumptions to validate, not current capabilities: the operator has a reachable
Navidrome server and authorized account; the indexed library overlaps that account's
visible library; enough tracks have usable lyrics; the chosen embedding model captures
the desired theme. The example prompt is user intent, not a factual assertion about
the seed song's interpretation or guaranteed matches in an installed library.

## Application Boundary and Delivery Scope

### Confirmed Direction

CLI is the first interface to shared application operations. FastAPI and a future
FastMCP server are additional adapters around those operations, not alternative homes
for business logic. The PoC HTML calls FastAPI; it does not call the CLI or contain
business rules.

The ingestion flow becomes: Navidrome listing and lyric APIs → shared ingestion →
chunking/embeddings → Qdrant, with the Navidrome song ID on every section. Playlist
creation uses those IDs directly. Resonance does not read audio files or infer IDs
from filenames in this workflow; Navidrome retains access to its own music storage.

Application inputs/results and errors must be usable without `Request`,
`HTTPException`, argparse, browser state, or MCP types. Adapters translate transport
inputs, obtain the caller context, invoke the operation, and render the result.
Library ingestion, authorization policy, validation, ordering, persistence, and
save reconciliation belong in the shared application implementation. Navidrome HTTP
and Qdrant access sit behind its dependencies.

This direction supersedes the historical "no services layer" convention for this
feature. A shared application layer does not require splitting the deployment into
multiple processes. Search and ingestion operations already live in this layer; do not
refactor them merely to add the PoC UI.

### PoC Scope

Single-account/library scope and API-based ingestion are confirmed. The other reductions remain
proposals for review rather than decisions already validated:

| Capability     | Current PoC/backend                                           | Product direction / later work                                        |
| -------------- | ------------------------------------------------------------- | --------------------------------------------------------------------- |
| Identity       | One operator-configured Navidrome account                     | User identity, account mapping, and multi-user authorization          |
| Administration | CLI/FastAPI library selection, collection creation, ingestion | Admin UI, ingestion progress/cancel/retry, full refresh               |
| User discovery | Semantic lyric search with supporting results                 | MCP search and candidate generation from user-approved context        |
| Playlist       | Private playlist save exists through CLI/FastAPI              | MCP-approved creation, preview/edit flow, downstream playback handoff |
| Interface      | Minimal local HTML PoC for operator testing                   | User-facing UI and MCP adapter over shared application operations     |

Navidrome credentials remain in the local ignored `.env`; the browser page never receives them. The configured API operator token is supplied locally by the operator. Existing private-playlist save implementation and SQLite operation journal remain available to CLI/API callers but are not expanded by this PoC.

### Ingestion and Search Contract

- Enumerate only the operator-selected music folder with paged
  [search3](https://opensubsonic.netlify.app/docs/endpoints/search3/) calls. Do not
  silently ingest every library visible to the account.
- Fetch [structured lyrics by song ID](https://opensubsonic.netlify.app/docs/endpoints/getlyricsbysongid/).
  Convert synced line timestamps to the existing chunker's domain input. Handle
  language variants and offsets explicitly; skip/report missing or unsynced-only
  lyrics without inventing timestamps or silently falling back to local files.
- Store source/server identity, music-folder ID, and Navidrome song ID on every
  indexed section. Preserve metadata and lyric evidence; filesystem paths are not
  ingestion requirements or identity. Deduplicate search by server/song ID.
- Record source scope, schema version, profile/model/dimensions in collection
  metadata. Navidrome-native collections are supported; old file-based collections
  require reingestion and are not searched by current code.
- Bind each collection to **Navidrome instance + library ID + embedding profile**.
  A readable name such as `home_english_bge_m3` is a label; metadata is authoritative.
  Library renames do not change identity. Record the actual model/revision and relevant
  embedding settings, not only a mutable config filename; equal dimensions do not
  prove compatible models. Store chunking settings and index generation as well.
- Build or reuse a Navidrome-native collection through the current API ingestion flow. Do not
  guess missing song IDs from filenames/titles or automatically delete/re-embed data.
- Keep incremental-ingestion readiness: use deterministic section point IDs and retain
  source/song identity, a normalized lyric-content hash, an indexing-configuration
  fingerprint, section position/count, and indexing time. Repeating the same input
  must not create duplicate points; a partial write must not imply a complete song.
  Safe additive re-ingestion is supported; changed/deleted-track reconciliation is
  future scope. A partial listing must never trigger deletion of apparently absent songs.
- Treat Navidrome IDs as authoritative within the configured server instance, not
  globally or forever across server rebuilds. Scope stale-ID checks accordingly and
  rebuild/reconcile the index after an identity-changing server rebuild.
- Resonance does not require a **music** bind mount. Qdrant, model-cache, and
  optional save-journal volumes have separate purposes. Local M3U creation has been
  removed; Navidrome playlist creation is the supported existing save path.

## Product Direction and Follow-On Scope

### Assistant-led user workflow

The product goal is to let a user ask an LLM for music that fits the context of their
conversation (for example, songs related to a mood or theme). Resonance exposes
user-oriented operations as MCP tools: search the user's indexed Navidrome library,
return ranked songs with supporting lyric evidence, and create a private playlist from
an explicitly approved ordered selection. A separate playback client or playback MCP
can then play that playlist. Resonance does not control playback.

Conversation context is supplied by the LLM as explicit search/theme input; Resonance
does not need access to the full conversation. Search results and generated candidates
are suggestions, not claims about a song's definitive meaning. Playlist writes require
clear user intent/approval, use the caller's authorized account, and return the created
playlist identity/status for downstream playback.

Keep administrative capabilities separate from user tools. Library discovery for
setup, embedding profile configuration, collection creation, ingestion, and future
refresh are operator/admin operations. Ordinary user/MCP credentials must not gain
ingestion or configuration authority. CLI, HTTP, and MCP remain adapters over the same
transport-independent application operations; MCP tools must not call CLI subprocesses
or route handlers.

The current one-account configuration is an operator-owned Navidrome account, not a
per-user identity integration. Before exposing tools to multiple users, define how a
caller identity maps to a Navidrome account and library, how playlist ownership is
enforced, and how credentials are isolated. Do not treat a shared operator token as
end-user authentication.

### Authentication direction

Navidrome is a music server, not a general OIDC identity provider. Its externalized
authentication feature delegates login to a reverse proxy/auth service (which may use
OIDC) and trusts a configured user header from trusted sources. Navidrome also has an
experimental, optional Jellyfin-compatible API with a username/password login that
returns a Navidrome JWT; this is a music-client API, not an OIDC authorization flow or
a portable “Login with Navidrome” integration. See Navidrome's [externalized auth
docs](https://www.navidrome.org/docs/usage/externalized-authentication/) and
[Jellyfin API docs](https://www.navidrome.org/docs/usage/features/jellyfin/).

For a future multi-user UI, evaluate an external OIDC provider/reverse proxy or a
Resonance-owned OIDC client/session. Treat Navidrome credentials and Resonance user
identity as separate concerns. The local operator PoC has no user login and must not
be exposed as a network-facing multi-user UI.

These capabilities need separate scope after the current PoC. They guide the shared
application contracts but are not all part of the current implementation batch.

### Embedding Runtime and Collection Naming Cleanup

Text Embeddings Inference (TEI) serves the configured Hugging Face model and exposes
an OpenAI-compatible embeddings endpoint. It does not route requests to Ollama. Ollama
uses its own `/api/embed` request protocol. If this deployment remains TEI-only, a
follow-on cleanup can remove the Ollama implementation and the `type: openai`/`type:
ollama` factory switch, leaving one thin OpenAI-compatible client. Keep the selected
endpoint, model ID, expected dimensions, optional pinned model revision, and credentials
when the chosen endpoint requires them. Model and dimensions alone do not specify where
to send a request or which API protocol to use.

Use the caller's collection name as a namespace and incorporate a normalized model
label and output dimension in the physical Qdrant collection name, for example
`english_vyakyarth_768`. Keep source/library scope and the complete embedding/index
fingerprint as authoritative metadata; a readable name alone cannot distinguish model
revisions, endpoints, or chunking settings. Qdrant supports collection-level metadata
in versions 1.16 and later ([collection metadata](https://qdrant.tech/documentation/manage-data/collections/#collection-metadata)).
A follow-on migration can move the current reserved metadata point into collection
metadata and adopt the namespace/model/dimension name. Do not rename or reindex existing
collections implicitly.

### Full Per-Library Refresh (Future)

Users will eventually need full reconciliation when songs or lyrics change or disappear.
The current operation already supports safe additive re-ingestion: it adds newly visible
usable tracks and skips unchanged, completely indexed ones in the selected collection.
It does not replace changed lyrics, update metadata-only changes, remove deleted or
inaccessible tracks, or schedule runs. Design those behaviors separately; do not assume
the server supplies a reliable change feed or lyrics-modification timestamp.

The current feature must leave the necessary state in Qdrant payloads: song identity,
`lyrics_hash`, `index_fingerprint`, section position/count, and `indexed_at`. The hash
uses a versioned, canonical representation of the selected lyrics/timing; the indexing
fingerprint includes model, normalization, and chunking settings. Metadata-only changes
must not be confused with changed embedding input. A collection schema version identifies
this contract. The accepted architecture and validation records are linked above.

Use Qdrant as the source of truth for which sections actually exist. Initially derive
a song's indexing state from its matching section payloads, requiring the expected
complete section set and matching fingerprints rather than a bare `ingested=true` flag.
No separate SQLite track ledger or extra metadata collection is required now. Future
job checkpoints/leases may use SQLite independently of vector completion state.
Qdrant supports [JSON payload metadata](https://qdrant.tech/documentation/concepts/payload/)
and [upserts by stable point ID](https://api.qdrant.tech/api-reference/points/upsert-points).

### Semantic Generation and Evidence

Resolve a selected seed to a specific recording, with explicit ambiguity handling and
an explicit theme-only option when seed lyrics are unavailable. Automatic prompt
interpretation is optional; structured seed/theme input can establish the baseline.

Retrieve separate seed-section and theme candidate pools using the collection's
compatible provider/model/dimensions. Exclude metadata points; overfetch before
recording-level aggregation and deduplication. Grow bounded candidate windows until
there are enough eligible tracks, the library is exhausted, or a resource cap is
reached. Report shortfalls; repeated choruses must not increase a recording's weight.

Evaluate seed/theme weighting, aggregation, thresholds, alternate-recording policy,
and artist caps against seed-only/theme-only baselines. The proposed two-tracks-per-
artist cap in a ten-track list is an evaluation starting point. Never pad with irrelevant
tracks or silently relax a selected cap. Seed inclusion must be explicit. Record model,
ranking parameters, and stable tie-breaking; save retries do not regenerate candidates.

A later frontend shows component relevance, actual supporting lyric sections and their
source/position/timing, and current song accessibility. The user can remove/reorder before saving;
prompt submission or reranking never saves. Scores are not probabilities or proof of
authorial intent. Generated explanations must be grounded and labeled as interpretation.

Demonstrations require rights-permitted excerpts. Local-only mode must make no hosted
model calls; hosted configuration must explicitly disclose what text is sent and have
no silent cloud fallback. Model/lyric rights remain release gates in
[PRD-10](10-public-positioning-open-source-readiness.md).

### Updates and Sharing

Updates must target an exact owned playlist ID, pre-read the existing state, detect
intervening edits, and confirm replacement scope. Preserve prior contents for recovery;
do not promise atomic rollback across calls. Report partial failures without deleting
user playlists. Verify the complete resulting state after every mutation. The
[updatePlaylist contract](https://opensubsonic.netlify.app/docs/endpoints/updateplaylist/)
restricts updates to the owner and supports visibility changes; actual server ordering
and replacement behavior still require integration tests. Public sharing is opt-in.

## Tests and Acceptance Criteria

### Existing Backend Capabilities (Reconciled)

- [x] Paged Navidrome listing and structured lyric retrieval are implemented through
      shared application operations and CLI/FastAPI adapters.
- [x] API ingestion uses Navidrome without filesystem access, creates or reuses a
      source/library/profile-bound Qdrant collection, and stores deterministic section
      IDs, lyric hashes, index fingerprints, and completeness information.
- [x] Safe additive re-ingestion skips unchanged complete songs, can finish identical
      partial writes, and does not prune absent songs. Changed indexed lyrics return
      `refresh_required`; deleted/inaccessible-track reconciliation is not implemented.
- [x] Semantic search runs in shared application code and is exposed through CLI and
      FastAPI. The existing HTML page can search existing collections and display lyric
      excerpts.
- [x] A private Navidrome playlist save operation exists through CLI/FastAPI and has
      been runtime-tested. This PoC does not add playlist controls to the page.
- [x] The user reported the current suite passes: 86 tests in 4.47 seconds.

### Search and Ingestion PoC UI (Implemented)

- [x] The static page uses the local API URL and has one operator-token field for
      protected requests; it does not implement user login/roles, persist the token,
      request Navidrome credentials, or read `.env`.
- [x] The page loads and presents Navidrome libraries and existing collections. The
      operator can select one library and a compatible collection (or request a new
      collection by leaving its name blank).
- [x] The page can start a protected ingestion run using the selected library, optional
      collection name, configured embedding profile, and optional `max_tracks` bound
      (default 10; clearing it opts into the full library).
      It displays the returned collection, tracks seen/processed/unchanged, skipped and
      missing/unsynced lyric counts, and whether enumeration completed.
- [x] The page makes it clear that re-running adds new eligible tracks and skips
      unchanged tracks but does not reconcile changed lyrics or delete removed tracks.
      It offers no reset/delete-index action.
- [x] The newly created/selected collection becomes available to the existing semantic
      search form; results remain ranked and show artist/title, section, score, and lyric
      excerpt. Search and ingestion failures show actionable HTTP/API errors.
- [x] A newly created collection remains visible even if it contains only the metadata
      point; the page reports that no searchable tracks have been indexed yet. The current
      UI filters out collections with one point, so this behavior must be explicitly fixed.
- [x] The documented local workflow uses FastAPI debug mode on port 8000 and
      `python -m http.server 8080 --bind 127.0.0.1` from `ui/`. The docs state that the
      debug API CORS setting is restricted to those local UI origins and required for
      this separate-origin setup.
- [x] Full-library mode is clearly identified, confirms before submission, and explains
      that the synchronous endpoint has no progress display; a lost response can be
      retried against the same collection for unchanged/partial input.

### Later Generation and Update Gates

These apply when the corresponding follow-on scope is designed and implemented:

- [ ] Unit tests cover prompt/seed ambiguity, missing lyrics, explicit seed inclusion,
      model compatibility, ranking components, repeated-section overfetch, distinct
      recordings with identical titles, artist caps, shortfall reporting, and stable ties.
- [ ] A rights-cleared evaluation library and human-reviewed theme judgments demonstrate
      both seed and theme influence, compared with seed-only and theme-only baselines.
      Include the example intent if the licensed/user-supplied seed is available;
      otherwise mark that scenario blocked, never fabricate its lyric evidence.
      Numerical relevance/latency targets require a measured baseline and review.
- [ ] Preview can be edited without writes. Saved contents exactly match the final
      approved order, with no duplicate recording/server IDs and no silent substitutions.
- [ ] Updates cover ownership denial, concurrent edits, partial failures, retries,
      visibility changes, stale IDs, and readback mismatch without false success.
      Repeat actual first/next/final-track client playback after a real update; confirm
      an unintended account cannot modify the playlist. M3U import is not a substitute.
- [ ] Any future multi-account/server support extends identity tests to those cases
      without reusing IDs across server instances or skipping account visibility checks.
- [ ] Local-only mode makes no hosted-model requests; hosted mode discloses data flow;
      demonstrations have rights-permitted evidence and default logs omit sensitive text.

## Implementation Plan

The backend milestones and minimal HTML PoC are complete. See the
companion [PoC UI implementation plan](../plans/2026-10-25-prd09-search-ingest-poc.md).

### Completed Backend Milestones

- [x] Shared application operations, single-account Navidrome discovery, API ingestion,
      collection metadata, and semantic search are implemented.
- [x] Explicit private playlist creation and operation reconciliation are implemented
      for CLI/API use, but are not included in this UI slice.
- [x] The user confirmed browser playback through the original three-track probe; the
      exact client version/private indicator remains unrecorded.

### Search and Ingestion PoC UI

- [x] Add a simple token field and library/collection controls to `ui/index.html`.
- [x] Add safe collection creation/selection and ingestion result reporting using the
      existing protected `/api/ingest` operation.
- [x] Connect ingestion output to existing semantic search and document local run
      commands for the separate static server/API origins.
- [x] User reported successful ingestion and search with their configured services.

### Deferred Scope

- [ ] Design seed/theme generation, recording-level ranking, and evaluation separately.
- [ ] Write a future UI PRD for preview, editing, evidence, and playlist save status;
      Vue 3/TypeScript/Vite remains a possible later implementation.
- [ ] Specify playlist updates/public sharing and a FastMCP adapter independently.
- [ ] Design full refresh reconciliation for changed/deleted tracks and scheduling.
- [ ] Define MCP caller identity to Navidrome account mapping before multi-user use.

## Open Questions

- None for this PoC. Its initial run is bounded to 10 tracks by default; an empty limit
  opts into the full selected library, and an empty collection name uses the generated
  name. Exact playback client/version and displayed private indicator remain unrecorded
  for the later playlist-client acceptance gate.

Questions for the later generation/update milestones:

- Include the seed by default, exclude it, or require a choice on every request?
- Which ranking weights, duplicate-version policy, artist cap, and relevance thresholds
  produce useful lists on the actual library? What are acceptable latency and list size?
- Should updates replace the whole approved list or offer a separately specified merge
  mode? Draft baseline is explicit replacement, not implicit append.

## References

- [PRD-06 — FastAPI service (historical)](06-fastapi-service.md)
- [OpenSubsonic createPlaylist](https://opensubsonic.netlify.app/docs/endpoints/createplaylist/)
- [OpenSubsonic updatePlaylist](https://opensubsonic.netlify.app/docs/endpoints/updateplaylist/)
- [OpenSubsonic getPlaylist](https://opensubsonic.netlify.app/docs/endpoints/getplaylist/)
- [OpenSubsonic search3](https://opensubsonic.netlify.app/docs/endpoints/search3/)
- [OpenSubsonic getLyricsBySongId](https://opensubsonic.netlify.app/docs/endpoints/getlyricsbysongid/)
- [Live validation record](../plans/2026-10-25-navidrome-validation.md)

Protocol references and live API behavior reviewed 2026-10-25. The original playlist was
visible in the user's browser and audible playback/advancing was confirmed. The exact
browser version and its displayed private indicator remain unrecorded.

---

## Changelog

- 2026-10-25: Recorded the current code baseline and shared application architecture;
  proposed read-only mapping first, then create-only private saves. Separated semantic
  generation, frontend, MCP, and update scope; added a staged backend plan.
- 2026-10-25: Confirmed single-account/library scope and authorization for a live
  Navidrome probe. Kept SQLite and independent recording UUIDs as unresolved proposals.
- 2026-10-25: Switched the planned library source to Navidrome listing/lyric APIs;
  removed the independent recording UUID and file-mapping database. SQLite remains
  an option for save-operation records. Recorded actual listing, synced-lyric, private
  creation/readback, and user-confirmed playlist visibility checks.
- 2026-10-25: Added future per-library refresh scope and current schema readiness:
  deterministic point IDs, content/index fingerprints, section completeness, and
  Qdrant-owned indexing state. Kept refresh orchestration outside this feature.
- 2026-10-23: Initial draft — Navidrome-first semantic preview and verified server playlists.

- 2026-10-25: Completed the staged Navidrome backend implementation. Added normalized
  API discovery and synced-lyrics ingestion, source/model-bound Qdrant search, a
  transactional private-save journal, and shared CLI/FastAPI operations. A production
  CLI playlist was created and privately verified by exact-ID readback; same-key retry
  returned the same ID. The original browser-playback confirmation is recorded;
  browser version/private UI indicator and bulk library indexing remain open.
- 2026-10-25: Reconciled PRD-09 against the post-cleanup code. Narrowed the next slice to
  the existing search UI plus controls to create/select a collection and run safe
  additive ingestion for one selected Navidrome library. Clarified that this is not
  changed/deleted-track refresh, and deferred playlist UI, generation, Vue, and FastMCP.
- 2026-10-25: Kept the PoC UI intentionally personal and minimal: local API URL,
  in-memory operator-token field, library/ingestion controls, and semantic search only.
  Future Vue login, roles, and admin settings remain separate.
- 2026-10-25: Implemented and locally exercised the PoC HTML workflow. Added local
  token/library/ingest controls, searchable collection states, loopback-only dev hosting,
  restricted debug CORS, and local setup instructions.
- 2026-10-25: Clarified product boundary: ingestion is administrative; search and
  private playlist creation are user-oriented MCP capabilities, with playback handled
  by a compatible client/tool. Recorded Navidrome auth options and the need to define
  caller-to-Navidrome identity mapping before multi-user access.
