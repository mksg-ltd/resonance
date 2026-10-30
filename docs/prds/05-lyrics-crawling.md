---
status: superseded
author: mk
tags:
  [
    crawling,
    lyrics,
    ingestion,
    jellyfin,
    superseded,
    navidrome-api-replaced-source,
  ]
title: "Lyrics Crawling & Library Ingestion"
phase: launch
created: 2026-03-18
updated: 2026-10-27
---

# Lyrics Crawling & Library Ingestion

**Status**: Superseded by the Navidrome API ingestion path in PRD-09. The core need to
discover library tracks and obtain available lyrics is implemented through Navidrome;
local-file scanning, Jellyfin lyrics, external crawling, and the proposed manifest were
not delivered and are not current scope.

---

## Overview

Build a lyrics acquisition pipeline that can crawl and index a user's music library, regardless of whether LRC files already exist alongside the audio.

## Goals

- Support multiple lyrics sources (local LRC files, embedded metadata, external APIs)
- Work with Jellyfin library structure without requiring manual file copying
- Handle the common case: user has music but no LRC files at all
- Incremental ingestion — only process new/changed songs

## Non-Goals

- Building our own lyrics transcription/sync engine
- Supporting every music server (Jellyfin first, others later)
- Guaranteed lyrics coverage — some songs simply won't have lyrics available

## Design

### Lyrics Source Priority

1. **Local LRC files** — sidecar `.lrc` files next to audio (what we have now)
2. **Embedded lyrics** — many audio formats (MP3, FLAC, M4A) can carry lyrics in metadata tags (ID3 USLT/SYLT, Vorbis LYRICS)
3. **Jellyfin lyrics API** — Jellyfin may already fetch lyrics via its own plugins (LrcLib, etc.)
4. **External APIs** — LrcLib (open, free), Musixmatch (API key required), Genius (unsynced only)

### Library Discovery

Two approaches:

**Direct filesystem scan:**

- Walk the music directory structure (like we do now with `data/`)
- Match LRC files to audio by filename
- Extract embedded lyrics from audio metadata
- Pro: simple, no API dependency
- Con: needs filesystem access to the music library

**Jellyfin API scan:**

- Use Jellyfin's REST API to enumerate the library
- `/Items?IncludeItemTypes=Audio` → list all songs
- `/Items/{id}/Lyrics` → fetch lyrics if available
- Pro: works remotely, uses Jellyfin's own lyrics sources
- Con: depends on Jellyfin having lyrics, API rate considerations

### Incremental Ingestion

Track what's been ingested:

- Store a manifest (JSON or SQLite) mapping `filepath → hash → qdrant_point_ids`
- On re-run, skip unchanged files, process new/modified ones
- Handle deletions — remove orphaned vectors from Qdrant

## Implementation Plan

### Phase 1 - Local Filesystem

- [ ] Generalize `DATA_DIR` to accept any music library path
- [ ] Recursive directory walking (artist/album/song structure)
- [ ] Match `.lrc` files to audio files by name
- [ ] Extract embedded lyrics from audio metadata (mutagen library)
- [ ] Ingestion manifest for incremental updates

### Phase 2 - Jellyfin API

- [ ] Jellyfin API client (auth, library enumeration)
- [ ] Fetch lyrics via Jellyfin's lyrics endpoint
- [ ] Map Jellyfin item IDs to Qdrant point IDs
- [ ] Handle libraries with partial lyrics coverage

### Phase 3 - External Sources

- [ ] LrcLib API integration (free, open)
- [ ] Fallback chain: local LRC → embedded → Jellyfin → LrcLib
- [ ] Rate limiting and caching for external APIs

## Open Questions

- Should we extract audio metadata (genre, year, BPM) as Qdrant payload even if lyrics aren't available?
- How does mutagen handle the variety of embedded lyrics formats across MP3/FLAC/M4A?
- What percentage of a typical library has lyrics available from LrcLib?
- ~~Should the crawler run as a background service or on-demand CLI?~~
  **Decision (2026-03-19):** Exposed as `POST /api/ingest` endpoint in the FastAPI
  service (PRD-06). CLI retained as a convenience wrapper.

---

## Changelog

- 2026-03-19: Updated — crawler exposed as FastAPI endpoint (PRD-06), not standalone service.
- 2026-03-18: Initial draft
