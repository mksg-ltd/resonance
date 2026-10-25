# 001: Navidrome Library Source and Shared Application Operations

Date: 2026-10-25
Status: Accepted direction; implementation under review

## Context

Resonance began as a learning proof of concept using mounted audio files, LRC parsing,
and route-owned ingestion/search functions imported by CLIs. The intended product now
uses one Navidrome account/library, with CLI, FastAPI and a possible future MCP adapter
calling one application interface. Navidrome 0.64.2 supplies metadata, synced lyrics,
server song IDs and private native playlists through its APIs. The user removed the
music mount and approved refactoring the proof-of-concept architecture.

## Decision

Use Navidrome as the production library/lyric source. Normalize API data into small,
filesystem-independent domain models. Put orchestration/policy in shared application
functions; adapters own transport parsing, presentation and lifecycle.

Bind each Qdrant collection to a configured server/account/library and effective
embedding profile. Carry scoped Navidrome song IDs directly, without an independent
recording UUID or file-to-ID mapping ledger. Deterministic section storage keys and
content/index fingerprints support retry safety and later library refresh. Completion
is derived from complete coherent section sets, not a boolean on the first point.

Use SQLite only for the transactional playlist-save journal. Persist submitting before
the external mutation; unknown create outcomes never blindly create again. Verify an
exact returned playlist ID, including XML private visibility, owner and ordered entries.

Keep the working batch-embedding interface and TEI-compatible client unless a concrete
need justifies simplifying them. Preserve raw LRC tools and legacy M3U behavior separately.

## Alternatives

- Keep mounted-file discovery and add persistent UUID/path mapping: unnecessary when
  Navidrome is the source and already supplies authoritative IDs.
- Put orchestration in HTTP routes: couples CLI/MCP use to FastAPI transport details.
- Add a SQLite ingestion ledger now: duplicates Qdrant completion state and expands
  this feature into the explicitly deferred refresh/job-orchestration scope.
- Rewrite every provider/tool: does not improve the requested native library workflow.

## Consequences

Native ingestion/search requires a new explicitly selected collection and source-aware
metadata. Legacy collections stay readable and are not deleted automatically. No audio
mount is needed by the new source. CLI/HTTP can share behavioral tests using local
Qdrant and SQLite while mocking external services. General updates, refresh scheduling,
UI/MCP and semantic playlist generation remain separate work.
