---
phase: launch
status: ready
created: 2026-03-18
updated: 2026-03-19
author: mk
tags: [jellyfin, plugin, integration]
---

# Jellyfin Plugin Architecture Research

**Status**: Ready for Development

---

## Overview

Understand Jellyfin's plugin system to evaluate whether lrc-match can integrate directly as a Jellyfin plugin rather than (or in addition to) a standalone web app.

## Goals

- Understand Jellyfin plugin architecture (C#/.NET based)
- Evaluate feasibility of a "smart playlist" plugin
- Identify Jellyfin APIs for library access, playlist management, lyrics
- Determine if a plugin or external service approach is better for this use case

## Non-Goals

- Building the plugin in this PRD — this is research only
- Replacing Jellyfin's core functionality

## Design

Research areas:
1. **Plugin architecture**: how do Jellyfin plugins work? Lifecycle, APIs, UI extension points
2. **Relevant plugins to study**: existing lyrics plugins, smart collection plugins, recommendation plugins
3. **API surface**: REST API for library queries, playlist CRUD, user sessions
4. **Integration patterns**: plugin vs external service vs both (plugin as thin client to external Qdrant service)

**Decision (2026-03-19):** lrc-match is a standalone FastAPI service (PRD-06). The
Jellyfin plugin would be a thin UI client that renders inside Jellyfin's web interface
and calls the FastAPI endpoints over HTTP. The plugin does NOT talk to Qdrant directly.

Remaining research question: can Jellyfin plugins serve custom UI pages within the
Jellyfin web interface, or only extend existing ones?

## Implementation Plan

### Phase 1 - Research

- [ ] Read Jellyfin plugin development docs
- [ ] Study existing plugin examples (especially lyrics-related ones)
- [ ] Map out Jellyfin REST API endpoints for library and playlists
- [ ] Evaluate C# Qdrant client maturity

### Phase 2 - Decision

- [ ] Document pros/cons of plugin vs external service
- [ ] Prototype the simpler approach first
- [ ] Define integration architecture

## Open Questions

- Can Jellyfin plugins serve custom UI pages, or only extend existing ones?
- Is there a Qdrant C# client, or would the plugin need to HTTP to a Python service?
- How do other Jellyfin recommendation plugins work?

---

## Changelog

- 2026-03-19: Updated — architecture decision made. Plugin is a thin client to
  FastAPI service (PRD-06), not a standalone C#/Qdrant integration.
- 2026-03-18: Initial draft
