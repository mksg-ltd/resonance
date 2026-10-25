---
phase: launch
status: draft
backend_status: implementation-complete
backend_completed: 2026-10-25
backend_spec_branch: spec/navidrome-playlists
created: 2026-10-23
updated: 2026-10-25
author: strand
tags: [playlists, navidrome, semantic-search, lyrics]
---

# Navidrome-First Natural-Language Semantic Playlists

**Status**: Draft — for review, not ready for development

**Delivery boundary**: The semantic playlist workflow below is the destination.
The first milestones use Navidrome's APIs for library discovery and lyric ingestion,
then create a verified private playlist from an explicit selection. Frontend development and semantic
playlist generation are separate follow-on work; this PRD is not one implementation batch.

**Backend status**: The staged discovery, Navidrome ingestion/search, and explicit
private-save backend has been implemented and exercised. This does not complete the
semantic generation, preview UI, or broader product workflow described by this draft.
The [architecture decision](../adr/001-navidrome-application-boundary.md) and
[live/runtime validation record](../plans/2026-10-25-navidrome-validation.md) capture
the implementation contracts and evidence.

---

## Overview

Turn a prompt such as “songs similar to Earth Song by Michael Jackson, talking about
broken promises” into a previewable, ranked selection from the user's own library,
then save the approved selection as a real Navidrome playlist through its
Subsonic/OpenSubsonic API. Similarity means **lyric meaning**, not necessarily sound,
genre, tempo, or mood inferred from audio.

This draft proposes behavior and validation gates, not a commitment to implement
every item. Navidrome is the first and only required server for this proposal;
Jellyfin is not a dependency or acceptance target. Earlier Jellyfin-oriented PRDs
remain historical context, not requirements inherited by this feature.

## Goals

- Provide a shared Python application interface that CLI, FastAPI, and a future
  FastMCP adapter can call without duplicating business logic.
- Make Navidrome the source of track metadata, song identity, and available synced
  lyrics, removing Resonance's dependency on a mounted copy of the music library.
- Carry Navidrome song IDs through ingestion and search, then create a private
  playlist in the approved order and verify it by readback.
- Prove actual playback in a supported client before accepting the integration.
- Subsequently add seed/theme candidate generation and an editable frontend using
  the same application interface.

## Non-Goals

- Implementing this PRD as part of writing it, or changing existing M3U behavior.
- M3U export/import as a substitute for a server playlist.
- A Jellyfin plugin, multi-server synchronization, audio analysis, or streaming music
  discovery outside the user's library.
- Bundling a lyrics corpus, introducing a lyrics crawler, or promising relevance for
  tracks with no usable lyrics.
- A mandatory generative LLM or a claim that every semantic result is objectively correct.
- Building a Vue application or FastMCP server as part of the initial backend release.
- Updating existing playlists, public sharing, automatic prompt interpretation, or
  combined seed/theme ranking in the initial backend release.
- A per-library refresh command/API, scheduled ingestion, or full changed/deleted-track
  reconciliation in this feature. The ingestion schema must support these later.

## Current State and Implementation Gap

Facts checked against the repository on 2026-10-25:

- [LibraryScanner](../../src/resonance/scanner.py) discovers audio files, extracts
  embedded synced lyrics or sidecar LRC, and reads artist/title/album metadata.
- [Ingestion](../../src/resonance/routes/ingest.py) stores section vectors, lyric text,
  section position/timing, source, and library-relative `audio_path`. Qdrant point IDs
  are assigned to chunks; they are not stable recording or server song identities.
- [Search](../../src/resonance/routes/search.py) embeds one text query and retrieves
  `limit` section hits, then deduplicates by `artist|title`. Repeated sections can
  leave fewer unique songs than requested; distinct recordings can be conflated.
- [Playlist creation](../../src/resonance/routes/playlists.py) writes a local M3U
  from submitted paths. It does not create a Navidrome playlist or verify playback.
- The inspected routes and embedder factory have no Navidrome adapter, seed-resolution
  flow, combined ranking, persistent song-ID mapping, or save-operation reconciliation.
- FastAPI already exposes search, ingestion, collections, configuration, health, and
  M3U creation. The CLI tools reuse `run_ingest()` and `run_search()`, although those
  functions currently live in HTTP route modules. The project is not CLI-only.
- [The current UI](../../ui/index.html) is a single HTML file with collection selection,
  text search, score filtering, and lyric excerpts. It has no selection, ordering,
  playlist creation, or Navidrome controls.
- Main settings currently come from environment variables; named provider YAML files
  load from `config/` or `~/.config/resonance/`. Historical README/config descriptions
  are not the implemented configuration contract. Ingestion is incremental by default;
  collection recreation requires `force=true`.

Baseline checks: 80 tests passed with external APIs mocked; Ruff lint and type checking
passed. The formatter flags an existing issue in `parser.py`. These checks do not
establish live Qdrant, embedding-provider, Navidrome, or playback compatibility.

The existing implementation is a learning proof of concept. Reuse useful chunking,
embedding, and Qdrant work, but improve product boundaries rather than preserving every
filename assumption, module split, or CLI argument. The new Navidrome workflow replaces
mounted-file ingestion; adapting the old interfaces is part of that migration.

At the initial baseline the user had removed the music bind mount from Compose and
deleted the separate development Compose file. The staged backend implementation below
now replaces native ingestion/search with the Navidrome APIs and removes stale Makefile
references. Legacy M3U and raw-LRC tools retain their separate filesystem behavior.

The existing `embedders/base.py`, `ollama.py`, and `openai.py` layout is also flexible.
TEI is the current serving direction. Keep a small batch-embedding contract and actual
model provenance; simplify/collapse the current provider implementation if useful.
Preserving a speculative provider framework is not a prerequisite for this feature.
TEI supports both its native API and an OpenAI-compatible embedding interface
([official quick tour](https://huggingface.co/docs/text-embeddings-inference/en/quick_tour)).

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
for business logic. The eventual frontend calls FastAPI.

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
multiple processes. Extract existing search/ingestion operations when needed by the
new workflow; avoid making a repository-wide refactor a prerequisite.

### Proposed First Backend Release

Single-account/library scope and API-based ingestion are confirmed. The other reductions remain
proposals for review rather than decisions already validated:

| Area       | First backend release                                                 | Later work                                      |
| ---------- | --------------------------------------------------------------------- | ----------------------------------------------- |
| Deployment | One configured server, saving account, and library                    | Multiple accounts/servers                       |
| Ingestion  | Paged Navidrome metadata and synced-lyric APIs; no music bind mount   | Additional library sources                      |
| Identity   | Server-scoped Navidrome song IDs stored directly in Qdrant            | Cross-server identity reconciliation            |
| Selection  | Explicit ordered song IDs; existing search can help the caller choose | Seed/theme generation and prompt interpretation |
| Save       | Create a new private playlist and verify it                           | Updates, merges, public sharing                 |
| Interfaces | CLI first, then a thin FastAPI adapter                                | Vue UI and FastMCP adapter                      |

There is no separate recording UUID or local-file-to-song mapping database in this
version. SQLite is an acceptable implementation choice for a durable **save-operation
journal**, so duplicate submissions and unknown write outcomes can be reconciled.
Search retries are read-only and need no journal. Choose the simplest transactional
implementation for saves; SQLite does not become a prerequisite for discovery/search.

Navidrome credentials are provided through the local, ignored `.env` file. Single-
account/library integration testing is authorized. Initial creation privacy has been
checked on the version above. The operator later confirmed browser playback of the
original three-song probe; its browser version and displayed privacy indicator were
not recorded.

The first independently deliverable milestone is **read-only API discovery and lyric
retrieval**, followed by API-based ingestion and removal of the music mount. Verified
playlist creation is the next bounded milestone; the full workflow is not one batch.

### First Release Workflow and Contract

1. List tracks in the configured Navidrome library and ingest their usable lyrics.
   Associate the resulting collection with that server/account/library and model.
2. Supply an explicit ordered selection of Navidrome song IDs. This can come from a CLI
   selection file or API request; there is no automatic semantic playlist builder yet.
3. Validate every selection against the configured server/library and saving account.
   Return missing, stale, or inaccessible entries without writing a playlist.
4. Confirm the exact ordered selection, name, owning account, and private visibility.
   Removal/reordering changes the submitted selection; the application never silently
   substitutes or omits tracks.
5. Create using a durable operation ID, then read back the exact returned playlist ID.
   Return verified state only when owner, visibility, name, count, and ordered song IDs
   match. A timeout or mismatch is an unresolved/unverified operation, not success.

Proposed shared operations are `inspect_connection`, `list_tracks`, `ingest_library`,
`validate_selection`, `create_playlist`, and `get_operation`. Names and DTOs remain
design proposals. `create_playlist` repeats validation before mutation; an earlier
search result is not indefinite approval to save a stale or inaccessible song ID.
A CLI or HTTP caller uses the same operation and policy.

Reject duplicate server song IDs. Distinct
recordings with identical artist/title remain distinct selectable entries. Updating
or overwriting a playlist is never inferred from a matching name; a duplicate-name
create requires explicit acknowledgment.

### First Release Ingestion and Identity Contract

- Enumerate the explicitly configured music folder with paged
  [search3](https://opensubsonic.netlify.app/docs/endpoints/search3/) calls. Do not
  silently ingest every library visible to the account.
- Fetch [structured lyrics by song ID](https://opensubsonic.netlify.app/docs/endpoints/getlyricsbysongid/).
  Convert synced line timestamps to the existing chunker's domain input. Handle
  language variants and offsets explicitly; skip/report missing or unsynced-only
  lyrics without inventing timestamps or silently falling back to local files.
- Store source/server identity, music-folder ID, and Navidrome song ID on every
  indexed section. Preserve metadata and lyric evidence; filesystem paths are not
  ingestion requirements or identity. Deduplicate search by server/song ID.
- Record source scope, schema version, provider/model/dimensions in collection
  metadata. Reject incompatible collections; do not mix old file-based payloads
  and new Navidrome-native payloads in the same workflow.
- Bind each collection to **Navidrome instance + library ID + embedding profile**.
  A readable name such as `home_english_bge_m3` is a label; metadata is authoritative.
  Library renames do not change identity. Record the actual model/revision and relevant
  embedding settings, not only a mutable config filename; equal dimensions do not
  prove compatible models. Store chunking settings and index generation as well.
- Build a new Navidrome-native collection as an explicit migration. Retain existing
  collections until the new source is verified; do not guess missing song IDs from
  filenames/titles or automatically delete/re-embed existing data.
- Prepare incremental ingestion now: use deterministic section point IDs and retain
  source/song identity, a normalized lyric-content hash, an indexing-configuration
  fingerprint, section position/count, and indexing time. Repeating the same input
  must not create duplicate points; a partial write must not imply a complete song.
  The refresh workflow itself is future scope. A partial listing must never trigger
  deletion of apparently absent songs.
- Treat Navidrome IDs as authoritative within the configured server instance, not
  globally or forever across server rebuilds. Scope stale-ID checks accordingly and
  rebuild/reconcile the index after an identity-changing server rebuild.
- Remove Resonance's **music** bind mount after API ingestion is validated. Config,
  Qdrant, model-cache, and optional save-journal volumes have separate purposes.
  The existing M3U endpoint remains a legacy explicit-path operation, outside the new flow.

### First Release Authorization and Save Safety

- Use a declared saving account and an explicit caller authorization boundary.
  Server credentials must not give arbitrary API callers the ability to save playlists.
  Keep credentials outside responses/default logs; require HTTPS except in an explicitly
  trusted local setup and validate the deployed server's authentication support.
- Prove private creation on the supported Navidrome version before enabling writes.
  The [createPlaylist contract](https://opensubsonic.netlify.app/docs/endpoints/createplaylist/)
  accepts repeated `songId` parameters but does not document a `public` parameter.
  A follow-up visibility update cannot retroactively guarantee initial privacy.
- Keep durable operation records bound to caller/account, server, approved recording
  and song order, name, and visibility. Same-key retries return/reconcile the recorded
  operation; a changed request with that key is rejected. Claim operations transactionally
  so concurrent submissions cannot both create.
- On timeout/crash after submission, an unknown outcome remains unresolved. Never
  blindly create again or identify an operation by playlist name. With a known ID,
  retry [getPlaylist](https://opensubsonic.netlify.app/docs/endpoints/getplaylist/)
  readback and compare the complete intended state. Inspect Subsonic errors as well
  as HTTP status; mismatches stay unverified.
- Do not put lyrics, prompts, local paths, or credentials in default logs. Read-only
  protocol probes and playlist saves need no embedding/LLM calls. Actual ingestion
  uses the explicitly configured local/hosted embedder with disclosed data flow.

## Follow-On Product Direction

These capabilities need separate scope after the first backend release. They are
retained here to guide the application contracts, not as first-release requirements.

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

### Per-Library Ingestion Refresh

Users will need to refresh a Navidrome library when songs or lyrics are added. The
future workflow should add new usable tracks and skip unchanged, completely indexed
ones for the selected collection/model scope. Changed-lyrics replacement, metadata-only
updates, deleted/inaccessible tracks, retries, and scheduling require that future scope.
Do not assume the server supplies a reliable change feed or lyrics-modification timestamp.

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

These are production application gates. The live protocol spike above establishes
server behavior, but is not an implementation of the shared application interface.

### First Milestone: Read-Only Integration

- [ ] CLI can inspect the configured connection, enumerate only the selected library
      with correct paging, and retrieve structured lyrics through shared operations.
- [ ] Tests cover failed envelopes, auth denial, paging duplicates/interruption, missing
      lyrics, unsynced-only/multiple-language variants, lyric offsets, and inaccessible
      songs. Read-only discovery never invokes a playlist mutation.
- [ ] The reusable adapter reproduces the version-recorded protocol probe. Unknown
      behavior remains explicit rather than inferred from titles or filenames.

### Next Milestone: API-Based Ingestion

- [x] Ingestion obtains metadata/lyrics through Navidrome without filesystem access.
      It stores source/folder/song IDs and compatible model/schema metadata in Qdrant.
- [x] Section payloads carry the refresh-readiness fields above; IDs and hashes are
      deterministic. Repeating unchanged ingestion does not duplicate points; partial
      writes cannot be classified as fully indexed merely because one section exists.
      A partial scan cannot silently remove existing indexed songs.
- [x] Search returns song IDs and deduplicates by server/song identity, preserving
      distinct recordings with identical titles. Existing collections are retained
      during explicit migration to a separate Navidrome-native collection.
- [x] CLI and FastAPI invoke the same application operation; the deployed ingestion
      path works after removing Resonance's music bind mount. Legacy M3U behavior
      remains an explicitly separate path rather than a dependency of native playlists.

### First Backend Release: Verified Private Creation

- [x] Application operations are callable without FastAPI or CLI imports. CLI and HTTP
      adapter tests show the same ordering, validation, and save-operation outcomes.
- [x] Selected server/folder scope and current song accessibility are validated.
      Legacy payloads without server song IDs cannot be saved by guessing a mapping.
- [x] All selected entries must validate; duplicate server song IDs are rejected.
      Save order equals the explicit approved selection, with no silent substitutions.
- [x] Mocked tests cover authorization denial, safe private creation, duplicate names,
      concurrent/repeated submissions, durable restart recovery, transport timeouts,
      failed Subsonic envelopes, stale song IDs, omitted JSON visibility, and readback mismatches.
- [x] A same-key retry cannot issue a second create after an uncertain outcome;
      a changed payload with the same key is rejected. Known-ID operations can retry
      readback without creating again.
- [x] On a version-recorded test server, create a real private playlist and read back
      exact ID, owner, visibility, name, count, and ordered entries. Prove private
      creation before enabling it; setting private after public creation is insufficient.
- [x] The user confirmed audibly playing and advancing through the original
      three-track probe in a browser. An unintended caller is denied by the new native
      save authorization boundary.
- [ ] Record the exact browser/client version and verify its displayed private
      indicator; this information is still outstanding.
- [x] Playlist saves make no embedding/LLM requests. Ingestion uses only the explicitly
      configured embedding provider. Default logs exclude credentials, prompts, full
      lyrics, and local paths; the new workflow does not require a music mount.

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

The staged implementation has delivered the shared operations, discovery CLI,
API-based ingestion/search, private-save journal, and thin CLI/HTTP save adapters.
The validation record linked above describes production and isolated runtime checks.

### Phase 1 - Establish the Shared Interface

- [x] Settle the single-account/library backend scope, shared application operations,
      caller policy and save-journal persistence. The Navidrome version is recorded.
- [ ] Record the exact playback client version; it remains unknown.

### Phase 2 - Navidrome Discovery and API Ingestion

- [x] Implement connection inspection, paged listing, and structured-lyric retrieval
      through the shared application interface and first CLI adapter.
- [x] Feed Navidrome-native tracks into shared ingestion, preserve server song IDs
      through search, and validate a new collection with fixture APIs and local Qdrant.
      No bulk live collection index was run.

### Phase 3 - Create and Verify

- [x] Implement durable create-operation handling, private-creation preflight,
      exact readback, and thin CLI/HTTP adapters.
- [ ] Record the exact supported browser/client version and confirm the private
      indicator in that client. Browser playback/advancing through the original probe
      was user-confirmed; the complete versioned client acceptance gate is unrecorded.

### Follow-On Scope

- [ ] Design seed/theme generation, recording-level ranking, and evaluation separately.
- [ ] Write a frontend PRD for discovery, selection, ordering, evidence, and save status.
      FastAPI + Vue 3/TypeScript/Vite is the current recommendation, not a dependency
      of the backend milestone.
- [ ] Specify playlist updates/public sharing and a FastMCP adapter independently.
- [ ] Scope per-library ingestion refresh separately, using the identity/fingerprint
      contract introduced now. No refresh endpoint, scheduler, or pruning is built here.

## Open Questions

- Does the proposed create-only first release match the desired milestone? Single-
  account/library scope is confirmed; the full semantic workflow is not one batch.
- Which client/version is the first supported playback target? Server 0.64.2 and
  initial private creation are tested; audible playback still needs confirmation.
- Settle the caller authorization policy and save-journal location. SQLite is allowed
  for transactional save records; local-file mapping and separate UUIDs are removed.
- Define lyric-language selection and unsynced-only reporting before migrating
  ingestion. Version the canonical hashing/payload contract now; full refresh behavior
  is later scope. English folder 2 is the tested library.

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
