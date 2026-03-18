---
phase: launch
status: ready
created: 2026-03-18
updated: 2026-03-18
author: mk
tags: [ui, django, jellyfin, playlists]
---

# Smart Playlists UI

**Status**: Ready for Development

---

## Overview

Build a web UI for creating "smart playlists" — describe a mood, theme, or feeling in natural language and get a playlist of matching songs from the Jellyfin library.

## Goals

- Django-based web interface for semantic lyric search
- Generate playlists from natural language descriptions
- Integration path with Jellyfin (play results directly)
- Support filtering by artist, mood, section position (openings, closings)

## Non-Goals

- Replacing Jellyfin's existing UI
- Real-time streaming or playback within the app (Jellyfin handles that)
- Mobile app — web-first

## Design

User flow:
1. User types "songs about letting go and moving on"
2. App embeds query, searches Qdrant, returns ranked song sections
3. Results grouped by song (deduplicate multiple sections from same song)
4. User can save as playlist, export to Jellyfin

Tech stack:
- Django for backend + templates (or something simpler if Django is overkill)
- Qdrant for vector search
- Jellyfin API for library metadata and playlist creation

## Implementation Plan

### Phase 1 - Core

- [ ] Django project setup with search endpoint
- [ ] Search form → results page with lyrics preview
- [ ] Artist filter support
- [ ] Result deduplication (group sections by song)

### Phase 2 - Jellyfin Integration

- [ ] Jellyfin API client for library metadata
- [ ] Map search results back to Jellyfin media items
- [ ] Create/export playlists to Jellyfin
- [ ] Pull LRC files directly from Jellyfin instead of local copy

## Open Questions

- Is Django the right choice or would something lighter (FastAPI + HTMX) be better?
- How does Jellyfin's playlist API work? Can we create playlists programmatically?
- Should we support "seed song" playlists? (pick a song, find similar)

---

## Changelog

- 2026-03-18: Initial draft
