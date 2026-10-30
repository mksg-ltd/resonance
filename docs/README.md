# Project documentation

Resonance began as a learning project: experiment with text embeddings, lyric chunking,
and Qdrant retrieval, then see whether those pieces could support useful music
discovery. The product has since moved from local files and early playlist experiments
to Navidrome as the source of song identity, metadata, and synced lyrics.

That evolution is part of the public project record. Earlier plans and experiments are
kept for context; they do not describe current supported behavior unless the current
README, roadmap, and source confirm it.

## Current project

Resonance provides a shared Python application layer, a FastAPI API, a Vue interface,
and CLI commands. The operator configures an embedding profile and indexes an
accessible Navidrome library into Qdrant. A listener searches by meaning, reviews
lyric evidence, and can explicitly save a private playlist. Resonance does not play
audio. The FastMCP transport is a tool-free scaffold; MCP search and playlist tools
are not implemented.

Read the [root README](../README.md) for the learning overview, current capabilities,
and links into the implementation. Read the [v1 roadmap](roadmap.md) for remaining
acceptance and release gates.

## Document map

- [`prds/`](prds/) — product requirements and decisions, including pivots and
  superseded directions.
- [`plans/`](plans/) — implementation plans and records of completed work.
- [`adr/`](adr/) — architectural decisions that remain relevant to the codebase.
- [`roadmap.md`](roadmap.md) — current v1 status and acceptance checklist.
- [`INSTALLATION.md`](INSTALLATION.md) — self-hosted installation, operation, and
  data-handling guide.

PRDs and plans describe intent at the time they were written. Check their front matter,
the roadmap, and the current source before treating a proposal as implemented. The old
Jellyfin, local-file scanner, raw-LRC, and local M3U work records are historical; those
paths are not part of the Navidrome product.
