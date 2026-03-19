---
phase: launch
status: superseded
superseded_by: 06-fastapi-service.md
created: 2026-03-18
updated: 2026-03-19
author: mk
tags: [ui, django, jellyfin, playlists]
---

# Smart Playlists UI (Superseded)

**Status**: Superseded by [PRD-06 — FastAPI Service & Configuration](06-fastapi-service.md)

---

## Why Superseded

The Django web UI approach was replaced by an API-first architecture using FastAPI.
Search, playlist, and Jellyfin integration features are now API endpoints in PRD-06.
The Jellyfin plugin (PRD-04) will serve as the primary user-facing UI, rendering
inside Jellyfin's web interface and calling the FastAPI service. Swagger UI covers
dev/power-user needs in the meantime.

---

## Changelog

- 2026-03-19: Superseded — features folded into PRD-06 (FastAPI service)
- 2026-03-18: Initial draft
