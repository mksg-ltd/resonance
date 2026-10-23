---
phase: launch
status: draft
created: 2026-10-23
updated: 2026-10-23
author: strand
tags: [playlists, navidrome, semantic-search, lyrics]
---

# Navidrome-First Natural-Language Semantic Playlists

**Status**: Draft — for review, not ready for development

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

- Combine seed-track lyric similarity with explicit thematic intent rather than
  treating the entire prompt as an undifferentiated search string.
- Let users inspect evidence, remove tracks, and reorder the result before any write.
- Resolve library tracks to playable Navidrome song IDs without confusing recordings.
- Create or deliberately update a server playlist, verify it by readback, and prove
  actual playback in a supported client before calling the integration accepted.

## Non-Goals

- Implementing this PRD as part of writing it, or changing existing M3U behavior.
- M3U export/import as a substitute for a server playlist.
- A Jellyfin plugin, multi-server synchronization, audio analysis, or streaming music
  discovery outside the user's library.
- Bundling a lyrics corpus, introducing a lyrics crawler, or promising relevance for
  tracks with no usable lyrics.
- A mandatory generative LLM or a claim that every semantic result is objectively correct.

## Current State and Implementation Gap

Facts checked against the repository on 2026-10-23:

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

Assumptions to validate, not current capabilities: the operator has a reachable
Navidrome server and authorized account; the indexed library overlaps that account's
visible library; enough tracks have usable lyrics; the chosen embedding model captures
the desired theme. The example prompt is user intent, not a factual assertion about
the seed song's interpretation or guaranteed matches in an installed library.

## Design

### User Flow and Preview Contract

1. Enter the prompt, desired track count, and target library/collection. Show the
   inferred seed and theme separately; allow correction without requiring an LLM.
2. Resolve “Earth Song” / “Michael Jackson” to a specific library recording. Present
   ambiguous albums, live versions, or remasters for selection; never guess silently.
   Missing seed lyrics produces a clear option for theme-only search, not hidden fallback.
3. Generate candidates using both the selected seed's lyric sections and the theme
   “broken promises.” Display a ranked preview before any Navidrome mutation.
4. Each entry shows artist, title, album/version where known, component relevance,
   supporting lyric section, mapping/playability status, and why it was selected.
   Users can remove and reorder entries; the approved order is the save order.
5. Choose create-new or update an explicitly selected owned playlist. Confirm name,
   account, visibility, and replacement scope. Never infer update from a matching name.
6. Save via the server API, then read back the exact playlist ID. Show verified saved
   state only when contents and metadata match; otherwise show pending/error state.
   Integration acceptance additionally requires the real-client playback gate below.

“Preview” means inspecting the selection; an optional authorized audio audition may
use the server's normal playback facilities, not exposed credentials in browser URLs.
No save is triggered by prompt submission or reranking alone.

### Stable Identity and Mapping

- Introduce a durable library-scoped recording identity independent of Qdrant chunk
  IDs and display metadata. All lyric sections reference it. Persistence/schema and
  migration for existing collections are decisions still to be designed.
- Store mapping from `(library_id, track_id, server_instance)` to Navidrome `songId`,
  plus matching evidence, last validation, and stale/ambiguous state. Include account
  visibility in validation; a song visible to an administrator may not be playable
  by the saving user. IDs must not be reused across server instances.
- Prefer verified server identifiers or library-relative path correspondence under
  operator-configured root mappings. Container and Navidrome absolute paths may differ.
  Use recording identifiers and corroborating album/version/duration metadata when
  available. Artist/title alone is insufficient; ambiguous matches need confirmation.
- Preserve identity across re-ingestion. Define reconciliation for renamed/moved files,
  duplicates, changed tags, rescans, and server rebuilds; invalidate stale mappings
  rather than sending an old ID that now refers to another recording.
- Unmapped, missing, or inaccessible songs are visible but cannot be silently saved.
  Offer removal/replacement and a new approved preview; do not silently shorten a save.

### Candidate Generation, Ranking, and Diversity

- Retrieve separate candidate pools for seed-section similarity and theme similarity
  using the collection's compatible provider/model. Never mix incompatible vector
  spaces. Exclude metadata-only points and unusable/missing recordings.
- Overfetch section hits before track aggregation and deduplication. Grow the bounded
  candidate window until there are enough eligible distinct tracks, the library is
  exhausted, or an explicit resource cap is reached. Report shortfalls and reasons.
- Aggregate sections to recording-level scores without rewarding repeated choruses.
  Proposed baseline: normalized seed and theme scores with tunable weights, then
  diversity reranking. Weighting, section aggregation, and relevance thresholds need
  evaluation; they are not settled implementation details.
- Deduplicate by durable recording identity and validated server song ID, not just
  artist/title. Decide explicitly whether alternate recordings count as duplicates.
- Add a visible artist-diversity control. Proposed starting rule: at most two tracks
  per primary artist in a ten-track list, without padding with irrelevant songs.
  Explain any shortfall; do not silently relax the user's selected cap.
- Seed inclusion is an open product choice. Make the chosen include/exclude setting
  explicit in the preview and tests; do not assume inclusion is always desirable.
- Stable tie-breaking and recorded ranking/model parameters make an unchanged request
  reproducible against an unchanged index. Regeneration is distinct from retrying a save.

### Lyric Evidence and Privacy

Display the actual matching section and its source/position, with timestamps when
available, and distinguish seed similarity from thematic evidence. Scores are not
probabilities or proof of authorial intent. Any generated explanation must be grounded
in retrieved text, identified as interpretation, and must not invent quotations.

Use only rights-permitted excerpts in demonstrations. Do not put full lyrics, local
paths, prompts, or credentials in default logs. Embedding/search should support a local
provider; do not silently send lyrics or prompts to a hosted model. Disclose what each
provider receives, obtain explicit hosted-provider configuration, and allow local-only
operation without a cloud fallback. Model/weights and lyric rights are release gates
in [PRD-10](10-public-positioning-open-source-readiness.md).

### Navidrome API, Authorization, and Write Safety

The OpenSubsonic contract documents `createPlaylist` with repeated `songId` values
(and `playlistId` when updating), `updatePlaylist` for metadata/add/remove operations,
and `getPlaylist` with `id` for readback. `updatePlaylist` restricts updates to the
owner. These are protocol facts, not proof of behavior on the deployed Navidrome version.

- Validate supported server/version, authentication method, ordering, and replacement
  semantics in a real Navidrome integration test. Use server-side credentials, HTTPS
  outside an explicitly trusted local setup, redacted logs, and supported token/salt
  or negotiated authentication rather than exposing passwords to the UI. Do not assume
  every OpenSubsonic extension or scoped API key exists on every Navidrome release.
- Protect Resonance's save operation with an explicit caller authorization boundary;
  a shared server credential must not let arbitrary callers modify another user's list.
  Declare which Navidrome account owns created playlists and check ownership before updates.
- Set requested visibility explicitly; proposed default is private, public sharing
  opt-in. Since creation does not document a `public` parameter, verify a safe server
  creation default and any follow-up `updatePlaylist` transition. If privacy cannot be
  guaranteed during creation, block private save rather than briefly exposing it.
- Keep an operation ID/idempotency key associated with account, server, target ID,
  approved ordered song IDs, and metadata. Reuse returns/reconciles the same outcome;
  a changed payload with the same key is rejected. This is application behavior, not
  an assumption that the server API offers idempotency keys.
- A same-name playlist is not identity. Create-new may yield another same-name list
  only after explicit confirmation; update targets an exact owned ID. Never overwrite
  an unrelated playlist by name or append duplicates after a double click.
- On timeout, reconcile the recorded operation and server state before retrying. An
  unknown create outcome must remain unresolved rather than blindly creating again.
  Persistence and crash recovery for this operation record are open design decisions.
- Pre-read an update target; detect intervening edits and ask before replacement.
  Do not promise atomic writes or rollback across multiple API calls. Preserve prior
  contents for recovery; report partial failures without deleting user playlists.
- After every create/update, `getPlaylist` must confirm exact ID, owner, visibility,
  name, count, and ordered song IDs. HTTP success alone is insufficient; inspect the
  Subsonic response status/errors too. A mismatch remains unverified.

## Tests and Acceptance Criteria

Proposed feature gates; none is claimed to have been implemented by this draft:

- [ ] Unit tests cover prompt/seed ambiguity, missing lyrics, explicit seed inclusion,
      model compatibility, ranking components, repeated-section overfetch, distinct
      recordings with identical titles, artist caps, shortfall reporting, and stable ties.
- [ ] Identity tests cover different mount roots, file moves/re-ingestion, duplicate
      metadata, multiple servers, stale IDs after rescan/rebuild, and inaccessible songs.
- [ ] A rights-cleared evaluation library and human-reviewed theme judgments demonstrate
      both seed and theme influence, compared with seed-only and theme-only baselines.
      Include the example intent if the licensed/user-supplied seed is available;
      otherwise mark that scenario blocked, never fabricate its lyric evidence.
      Numerical relevance/latency targets require a measured baseline and review.
- [ ] Preview can be edited without writes. Saved contents exactly match the final
      approved order, with no duplicate recording/server IDs and no silent substitutions.
- [ ] Mock API tests cover auth/ownership denial, private/public metadata, duplicate names,
      repeated submissions, concurrent edits, transport timeouts, failed Subsonic envelopes,
      partial updates, stale mappings, and readback mismatches without false success.
- [ ] On a version-recorded Navidrome test instance, create and then update a real playlist
      through the API. Read back the exact ID and compare ordered entries and metadata.
      No M3U import or shared playlist directory is involved in this acceptance path.
- [ ] In a named/version-recorded supported client using the intended account, refresh,
      find the playlist, play the first track, advance to another, and check the final
      track resolves to the intended recording. Record actual audible playback and
      seek/advance failures; API readback or a stream HTTP 200 alone does not pass.
      Repeat after update; an unintended account cannot modify the playlist.
- [ ] Local-only mode makes no hosted-model requests; hosted mode discloses data flow;
      secrets and full lyric bodies are absent from captured default logs.
- [ ] Existing search and M3U tests continue passing without behavior changes.

## Implementation Plan

Tentative sequencing only; approval of this draft does not authorize implementation.

### Phase 1 - Resolve Contracts

- [ ] Select Navidrome/client versions, identity and persistence strategy, rights-cleared
      evaluation fixtures, authentication boundary, and seed/diversity defaults.
- [ ] Prove server mapping, private creation, exact replacement, and client playback.

### Phase 2 - Preview and Ranking

- [ ] Evaluate bounded multi-pool retrieval, aggregation, diversity, and evidence UX.

### Phase 3 - Verified Save

- [ ] Design retry reconciliation and ownership-safe writes; exercise all acceptance gates.

## Open Questions

- Include the seed by default, exclude it, or require a choice on every request?
- Which recording-identity strategy survives library moves, and where do mappings and
  idempotency records live without assuming Qdrant chunk IDs are stable track IDs?
- Which ranking weights, duplicate-version policy, artist cap, and relevance thresholds
  produce useful lists on the actual library? What are acceptable latency and list size?
- Which Navidrome release/client is the first support target, which account owns lists,
  and can that release guarantee private creation before any metadata follow-up?
- Should updates replace the whole approved list or offer a separately specified merge
  mode? Draft baseline is explicit replacement, not implicit append.

## References

- [PRD-06 — FastAPI service (historical)](06-fastapi-service.md)
- [OpenSubsonic createPlaylist](https://opensubsonic.netlify.app/docs/endpoints/createplaylist/)
- [OpenSubsonic updatePlaylist](https://opensubsonic.netlify.app/docs/endpoints/updateplaylist/)
- [OpenSubsonic getPlaylist](https://opensubsonic.netlify.app/docs/endpoints/getplaylist/)

Protocol references reviewed 2026-10-23. No live Navidrome or playback validation was
performed while writing this draft.

---

## Changelog

- 2026-10-23: Initial draft — Navidrome-first semantic preview and verified server playlists.
