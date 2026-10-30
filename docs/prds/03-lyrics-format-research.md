---
status: superseded
author: mk
tags: [research, lrc, lyrics, formats, superseded, file-based-path-retired]
title: "Lyrics Format Research"
phase: launch
created: 2026-03-18
updated: 2026-10-27
---

# Lyrics Format Research

**Status**: Superseded by Navidrome's structured-lyrics ingestion path and the removal
of local LRC ingestion in PRD-11. The original file-format research checklist was not
completed and is no longer an active product requirement.

---

## Overview

Research LRC format variants and alternative lyrics formats to improve parsing robustness and understand what metadata is available.

## Goals

- Understand LRC format variants (simple, enhanced, extended)
- Identify what metadata LRC files can carry beyond timestamps
- Survey alternative lyrics formats (SRT, ASS, LRCX, Synced Lyrics)
- Understand how Jellyfin stores and serves lyrics

## Non-Goals

- Building parsers for every format — focus on what's actually in the library
- Audio-based lyrics sync or recognition

## Design

Research areas:

1. **LRC variants**: simple `[mm:ss.xx]`, enhanced `[mm:ss.xx]<word timestamps>`, ID tags `[ar:Artist]`, `[al:Album]`
2. **Section tag conventions**: how standardized are `[Chorus]`, `[Verse]` markers? Are there other conventions?
3. **Jellyfin lyrics**: how does Jellyfin source lyrics? LRC providers? Embedded in audio metadata?
4. **Alternative formats**: do any formats carry richer structural metadata (verse/chorus annotations)?

## Implementation Plan

### Phase 1 - Core

- [ ] Audit existing LRC files for format variants and edge cases
- [ ] Document LRC ID tag usage (`[ar:]`, `[al:]`, `[ti:]`) in the collection
- [ ] Research Jellyfin lyrics plugin architecture
- [ ] Survey section tag conventions across LRC providers

### Phase 2 - Enhancements

- [ ] Extract ID tags for richer metadata (artist/album from file, not just filename)
- [ ] Handle enhanced LRC word-level timestamps if present

## Open Questions

- Do any of the 3,884 LRC files have ID tags we're currently ignoring?
- Are there LRC files with word-level timestamps that could improve chunking?
- What LRC provider does Jellyfin use? Can we influence which one?

---

## Changelog

- 2026-03-18: Initial draft
