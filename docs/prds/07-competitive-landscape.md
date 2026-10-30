---
status: superseded
author: mk
tags:
  [
    research,
    competition,
    audiomuse,
    plex,
    superseded,
    research-not-completed,
    absorbed-by-prd-10,
  ]
title: "Competitive Landscape Research"
phase: launch
created: 2026-03-18
updated: 2026-10-27
---

# Competitive Landscape Research

**Status**: Superseded as a standalone research PRD. The proposed comparisons were not
completed; the competitor-claims review is carried into the open-source readiness work
in PRD-10.

---

## Overview

Understand existing solutions for AI-powered music discovery and smart playlists to inform resonance's positioning and feature set.

## Goals

- Map the competitive landscape for semantic/AI music search
- Understand what AudioMuse AI and Plex AI Playlists offer
- Identify gaps that a self-hosted, lyrics-focused tool can fill
- Learn from their UX patterns and feature design

## Non-Goals

- Replicating their exact feature set
- Building audio analysis capabilities (our differentiator is lyrics)

## Research Areas

### AudioMuse AI

- What is it? How does it work?
- Audio-based or lyrics-based? Both?
- Open source or proprietary?
- What embedding/ML approach do they use?
- How do users interact with it? (UI, API, plugin)
- Pricing model

### Plex AI Playlists

- How does Plex's AI playlist generation work?
- What data does it use? (listening history, audio features, metadata, lyrics?)
- Is it cloud-dependent or local?
- Plex Pass requirement? Pricing?
- User reception — what do people like/dislike?
- How does it compare to Spotify's AI DJ?

### Other Players

- **Spotify AI DJ / Daylist** — mood-based, uses listening patterns + audio features
- **Apple Music** — editorial curation + some ML recommendation
- **Last.fm** — scrobble-based collaborative filtering
- **MusicBrainz / AcousticBrainz** — open metadata, audio feature analysis
- **Navidrome / Funkwhale** — self-hosted music servers, any smart playlist features?

### Our Differentiator

Key question: what can resonance do that none of these can?

Hypothesis:

- **Lyrics-semantic search** — no one does this well, most use audio features or listening patterns
- **Fully self-hosted** — no cloud dependency (Qdrant + Ollama + Jellyfin)
- **Thematic discovery** — find songs by meaning, not by sound or popularity
- **Cross-lingual** — find English songs matching a Persian poem (as we demonstrated)

## Implementation Plan

### Phase 1 - Research

- [ ] Deep dive on AudioMuse AI — docs, demos, architecture if available
- [ ] Deep dive on Plex AI Playlists — user reports, feature docs, Plex forums
- [ ] Survey self-hosted music server ecosystem for smart playlist features
- [ ] Compile findings into a comparison matrix

### Phase 2 - Positioning

- [ ] Define resonance's unique value proposition based on research
- [ ] Identify features worth borrowing vs. areas to differentiate
- [ ] Update project roadmap based on competitive gaps

## Open Questions

- Is anyone else doing lyrics-based semantic search specifically?
- Are there open-source projects in this space we could collaborate with?
- What's the overlap between Jellyfin users and people who'd want smart playlists?

---

## Changelog

- 2026-03-18: Initial draft
