---
status: superseded
author: mk
tags: [chunking, embeddings, accuracy, historical, learning-era]
title: "Chunk Size Tuning & Embedding Accuracy"
phase: launch
created: 2026-03-18
updated: 2026-10-27
---

# Chunk Size Tuning & Embedding Accuracy

**Status**: Superseded as a standalone learning experiment. The planned comparison
benchmark was not completed; search-match evaluation is now tracked with PRD-09 and
the v1 roadmap.

---

## Overview

Systematically evaluate how chunk size (gap threshold) and embedding model choice affect search accuracy for semantic lyric queries.

## Goals

- Find the optimal gap threshold for temporal chunking (currently tested 5s and 10s)
- Compare small vs large embedding models at the same chunk size to isolate each variable
- Build a repeatable benchmark with known-good query/result pairs

## Non-Goals

- Building a full evaluation framework — keep it simple scripts
- Optimizing for latency or cost at this stage

## Design

Create a benchmark set of queries with expected results (based on what we've validated manually):

- "boyfriend abused manipulated her" → Olivia Rodrigo, Shontelle, Katy Perry Pearl
- "resilience and empowerment" → Katy Perry Resilient, Madonna I Rise
- "what have we done to the world" → Earth Song, Everyday Life, Heal the World
- "shared humanity, we are all one" → Arabesque, Bani Adam

Run each query across different collection configs and compare rankings.

## Implementation Plan

### Phase 1 - Core

- [ ] Create `lyrics_10_small` collection (10s gap, small model) to isolate chunk size vs model
- [ ] Build benchmark script with query/expected-result pairs
- [ ] Test gap thresholds: 5s, 8s, 10s, 15s
- [ ] Document findings

### Phase 2 - Enhancements

- [ ] Explore Matryoshka truncation — large model at 1536d vs small model at 1536d
- [ ] Test hybrid chunking: use section tags when available, tune gap only for untagged songs

## Open Questions

- Is there a sweet spot where increasing chunk size starts to hurt? (too coarse = back to whole-song averaging)
- Should the benchmark weight abstract queries differently from literal ones?

---

## Changelog

- 2026-03-18: Initial draft based on manual exploration session
