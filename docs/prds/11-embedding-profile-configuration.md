---
phase: launch
status: approved-for-implementation
created: 2026-10-25
updated: 2026-10-25
author: strand
tags: [configuration, embeddings, cleanup]
---

# Proof-of-Concept Cleanup: Embedding Profiles and Legacy File Workflows

**Status**: Approved for implementation

## Overview

Replace user-maintained embedding YAML files in `config/` with a bundled catalog of
supported profiles. The operator selects an active profile and service URL in `.env`
for now; CLI and API callers can optionally override the profile by stable ID. The
catalog supplies model ID, expected dimensions, and protocol. Endpoint URLs and
credentials remain environment configuration.

Also remove the superseded local filesystem/LRC ingestion and M3U file-writing
paths. Navidrome API ingestion, shared lyric chunking, semantic search, and private
Navidrome playlist operations remain the supported product path. This cleanup does
not change indexed vectors, rename Qdrant collections, or alter Navidrome playlist
behavior.

## Current State

- `config/` currently contains named YAML files for OpenAI-compatible and Ollama
  models, plus examples. The YAML `type` selects the transport implementation.
- `resonance-ingest --provider <name>` uses the YAML filename stem. Search can
  resolve a compatible embedder from collection metadata.
- `OpenAIEmbedder` speaks the OpenAI embeddings protocol. It is used with OpenAI
  and OpenAI-compatible services such as Hugging Face Text Embeddings Inference
  (TEI).
- `OllamaEmbedder` speaks Ollama's distinct `/api/embed` protocol.
- Global application and service configuration already uses environment variables.
- The current deployment direction is TEI. An Ollama transport already exists in
  code; the catalog retains its known-good `nomic-embed-text` profile.
- FastAPI `/api/ingest` calls `application.ingest.run_ingest`, which retrieves
  Navidrome lyrics and invokes the shared chunker. `/api/search` calls
  `application.search.run_search`; its legacy collection read branch is removed by
  this cleanup.
- The separate `/api/playlists` route writes local M3U files. Navidrome playlist
  creation is a different route (`/api/navidrome/playlists`) and remains supported.
- Raw-LRC parsing, local file scanning, filename metadata fallback, and the
  `resonance-chunks` tool are not used by the Navidrome application flow.

## Goals

- Remove the top-level `config/` directory as the source of embedding profiles.
- Define supported embedding profiles in a version-controlled catalog shipped with
  Resonance.
- Select a catalog entry by stable profile ID at ingestion, replacing the YAML
  filename passed to `--provider`.
- Keep model identity and expected dimensions explicit and validated before
  indexing; retain model/profile provenance in Qdrant metadata.
- Keep service endpoint and secrets in environment configuration, not in the
  profile catalog or Qdrant metadata.
- Separate the model profile from the API transport and endpoint so Ollama and
  OpenAI-compatible profiles use their respective protocols and the configured URL.
- Keep profile selection consistent across CLI and application interfaces.
- Remove local audio-file scanning, embedded/sidecar LRC parsing, raw-LRC CLI
  visualization, legacy file-collection search behavior, and local M3U creation.
- Retain `LrcLine`/`LrcChunk` and shared chunking used by Navidrome ingestion. Gap
  splitting works on Navidrome timestamps. Literal section-tag splitting remains
  conditional on markers in lyric text; this cleanup does not invent section data.

## Non-Goals

- Automatically switching a running TEI instance between models.
- Changing embedding models, regenerating vectors, migrating collections, or
  changing collection naming in Qdrant.
- Replacing environment-based configuration for Navidrome, Qdrant, or the API.
- Adding a settings UI, runtime profile editor, or user-defined profile YAML.
- Redesigning embedding math, chunking, or the shared application boundary.
- Removing Navidrome library inspection, Navidrome playlist creation, or previously
  created M3U files from disk.

## Product and Configuration Contract

### Profile catalog

Each supported profile has a stable ID and declares, at minimum:

- model identifier;
- expected vector dimensions;
- transport/service kind, such as OpenAI-compatible or Ollama;
- optional model revision when it is known and useful for reproducibility.

The packaged YAML catalog is the allowlist of profiles that CLI and API callers may
select. It preserves configured profiles with explicit model and dimension values.
Unknown IDs fail with a clear supported-profile list before any collection is created
or modified. Profile IDs are stable identifiers, not config filenames or service
URLs.

The catalog is `src/resonance/data/embedding_profiles.yaml`. It must not require a
working-directory `config/` directory or user-home profile directory. Existing IDs
are retained where practical so stored Navidrome collection metadata continues to
resolve.

### Runtime service configuration

The selected profile is resolved against runtime environment settings. Endpoint URLs
and credentials are deployment-specific and are not stored in the static catalog.
For the TEI-first deployment, the service uses the OpenAI-compatible embeddings
protocol and the endpoint is supplied by the environment (for example, a Compose
service URL reachable from the Resonance container).

TEI loads a model when the TEI service starts. Selecting a Resonance profile does not
make TEI load or switch to another model. The configured profile's model must match
the model actually served at that endpoint, and returned vectors must match the
catalog's expected dimensions. A mismatch is reported as a configuration or embedding
error before vectors are written.

For an Ollama profile, the profile selects Ollama's `/api/embed` protocol, and the
runtime base URL may point to the Ollama service, for example `http://ollama:11434`
inside Compose. A TEI host such as `http://tei:80` does not imply Ollama transport;
TEI uses the OpenAI-compatible protocol. The service hostname and protocol are
separate configuration values.

### CLI and application behavior

- `.env` selects the active profile and service URL. CLI `--profile` can override
  the active profile for one operation. Retain `--provider` as a deprecated alias
  during this cleanup if practical.
- FastAPI ingestion uses the configured active profile when the request omits one;
  it accepts an explicit profile ID override. Search resolves the profile ID stored
  with the selected collection.
- Application operations receive a profile ID or resolved profile object rather
  than a path/name that implies a YAML file.
- Search continues to use the profile identity recorded in collection metadata when
  available. An explicit override must resolve to a known profile and be compatible
  with the collection's stored model/dimensions before a query is embedded.
- Profile metadata may retain a transport identifier and non-secret endpoint identity
  where needed to prevent incompatible operations. Credentials and secret values
  must never be persisted in Qdrant or logged.
- Existing Navidrome-native collections remain readable and are not migrated,
  renamed, or deleted. The explicitly obsolete file-based collection schema loses
  its legacy search branch; users must reingest through Navidrome to search those
  results.

### Removed legacy features

- Local audio-file scanning and embedded/sidecar-LRC extraction.
- Raw LRC file parsing and `resonance-chunks` visualization.
- `SongData`, filename-derived metadata, filesystem path payload compatibility, and
  legacy file-based collection search.
- `POST /api/playlists`, the local M3U writer, and its route-only filename helper.
- The `mutagen` dependency plus code, documentation, and tests used only by these
  removed behaviors.

Retain `LrcLine`, `LrcChunk`, gap and literal-tag chunking used by Navidrome lyrics,
Navidrome library/lyrics APIs, `resonance-playlist`,
`POST /api/navidrome/playlists`, the save journal, and Navidrome-native search.

## Acceptance Criteria

1. A fresh checkout can use supported embedding profiles by stable ID without a
   repository-local or home-directory `config/` directory.
2. Ingestion accepts a stable profile ID and rejects unknown IDs before mutating
   Qdrant, showing the available IDs in its error/help output.
3. Ingest and search resolve the same profile definition and verify actual response
   vector count and dimensions before Qdrant writes or result ranking.
4. The TEI profile uses the configured OpenAI-compatible service URL; profile
   selection does not claim to dynamically switch the model loaded by TEI.
5. Endpoint credentials are read from environment configuration and are absent from
   Qdrant metadata and normal logs.
6. Existing collections are neither renamed nor recreated; current model and
   dimension compatibility checks remain enforced.
7. Documentation and examples no longer instruct users to create embedding YAML in
   `config/` or `~/.config/resonance/`.
8. The `ollama-nomic-text` profile uses the distinct Ollama transport and its
   environment-provided base URL without filename-based configuration.

## Settled Implementation Decisions

- Ship a packaged YAML catalog containing stable profile IDs, model IDs, expected
  dimensions, and transport kind.
- Use `RESONANCE__EMBEDDING__PROFILE`, `RESONANCE__EMBEDDING__BASE_URL`, and
  `RESONANCE__EMBEDDING__API_KEY` for the active runtime service. The URL is used
  with the transport specified by the selected profile.
- Do not include `ollama-bge-m3` yet: its previous configuration omitted a
  verified dimension and the old embedder rejected it for indexing.
- Keep OpenAI-compatible and Ollama transport implementations for catalog entries;
  the URL does not infer protocol.
- Expose profile ID selection in CLI and FastAPI, with the old `--provider` and
  request field retained as compatibility aliases where practical.
- Preserve Navidrome-native Qdrant metadata compatibility. Remove filesystem-based
  legacy collection search support.
- Remove the listed local file/LRC and M3U features in this same cleanup.

## Relationship to Other Work

This cleanup follows the Navidrome backend milestone in
[PRD-09](09-navidrome-semantic-playlists.md) and removes proof-of-concept paths
superseded by that backend. It is intended to be independently reviewable before
beginning another larger product milestone.
The existing application/service boundary remains in place: CLI and future HTTP/MCP
adapters use the shared embedding/profile resolver rather than duplicating provider
selection logic.
