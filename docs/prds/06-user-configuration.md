---
phase: launch
status: ready
created: 2026-03-18
updated: 2026-03-18
author: mk
tags: [configuration, api-keys, models, ux]
---

# User Configuration — Models, API Keys & Embedding Options

**Status**: Ready for Development

---

## Overview

Let users configure their embedding model, API keys, Qdrant connection, and chunking preferences instead of hardcoding them.

## Goals

- Support multiple embedding providers (OpenAI, local models, etc.)
- Secure API key management
- Configurable chunking parameters
- Sensible defaults that work out of the box

## Non-Goals

- A full admin UI (config file or env vars is fine for now)
- Hot-reloading config changes — restart is acceptable
- Managing multiple users with different configs (single-user self-hosted)

## Design

### Configuration Hierarchy

```
defaults (code) → config file → environment variables → CLI flags
```

Each layer overrides the previous. CLI flags always win.

### Config File

```yaml
# ~/.config/lrc-match/config.yaml (or project-local config.yaml)
embedding:
  provider: openai          # openai | ollama | sentence-transformers
  model: text-embedding-3-small
  dimensions: 1536          # auto-detected for known models

openai:
  api_key: ${OPENAI_API_KEY}  # env var reference, never plaintext

ollama:
  base_url: http://localhost:11434
  model: nomic-embed-text

qdrant:
  url: http://localhost:6333
  api_key: null              # for Qdrant Cloud

chunking:
  gap_threshold_sec: 10.0
  min_chunk_lines: 2

library:
  music_dir: /path/to/music
  jellyfin_url: null
  jellyfin_api_key: null
```

### Provider Abstraction

```python
class EmbeddingProvider(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...
    @property
    def dimensions(self) -> int: ...
```

Implementations:
- `OpenAIEmbedder` — current approach, uses OpenAI API
- `OllamaEmbedder` — local models via Ollama (e.g., nomic-embed-text, mxbai-embed-large)
- `SentenceTransformerEmbedder` — direct HuggingFace models, no server needed

### Local Model Considerations

Users who are self-hosting everything may not want to depend on OpenAI:
- **Ollama** is the easiest path — already popular in homelab setups
- `nomic-embed-text` (768d) is a good local alternative — smaller but surprisingly capable
- Trade-off: local models are free but lower quality than OpenAI's large model

This matters for the project's identity — a fully self-hosted semantic search
(Jellyfin + Qdrant + Ollama) with zero cloud dependencies is a compelling pitch.

## Implementation Plan

### Phase 1 - Config File

- [ ] YAML config loading with pydantic model validation
- [ ] Environment variable expansion in config values
- [ ] CLI flags override config file
- [ ] Config discovery: project-local → user home → defaults

### Phase 2 - Provider Abstraction

- [ ] `EmbeddingProvider` protocol
- [ ] OpenAI implementation (extract from current code)
- [ ] Ollama implementation
- [ ] Dimension auto-detection for known models

### Phase 3 - Local Models

- [ ] Test and benchmark Ollama embedding models against OpenAI
- [ ] Document recommended local models and their trade-offs
- [ ] Handle dimension mismatch (re-ingestion required when switching models)

## Open Questions

- Should switching models trigger automatic re-ingestion, or just warn?
- Is pydantic-settings a better fit than raw YAML parsing?
- Should we support multiple collections with different models simultaneously (we already do this ad-hoc via CLI flags)?

---

## Changelog

- 2026-03-18: Initial draft
