---
phase: launch
status: ready
created: 2026-03-18
updated: 2026-03-18
author: mk
tags: [research, weaviate, vector-db, learning]
---

# Weaviate Exploration

**Status**: Ready for Development

---

## Overview

Study Weaviate as an alternative/complementary vector database to Qdrant, with focus on its built-in vectorizer module architecture — a fundamentally different approach to how embeddings are handled.

## Goals

- Understand Weaviate's architecture and how it differs from Qdrant
- Deep dive into the vectorizer module system ("DB owns the embedding")
- Evaluate if Weaviate's approach has advantages for lrc-match
- Hands-on: replicate the lyrics search with Weaviate for comparison

## Non-Goals

- Migrating away from Qdrant — this is learning, not a replacement decision
- Benchmarking at production scale

## Context: Why Weaviate is architecturally interesting

### The fundamental design question

Every vector database must answer: **where does the embedding responsibility live?**

This is the same class of question as "where does business logic live?" in web architecture
(fat models vs thin models, stored procedures vs application code). It's a system boundary
decision with cascading consequences.

**Qdrant's answer: the database is a storage+search engine.**
Qdrant receives vectors. It doesn't know or care where they came from. Like Postgres receiving
rows — the DB's job is to store and query efficiently, not to transform data. The embedding
model is an application concern.

**Weaviate's answer: the database is a semantic engine.**
Weaviate receives objects (text, images, structured data). It knows how to turn them into
vectors because vectorization is part of its pipeline. The embedding model is an infrastructure
concern, configured at the DB level, not the app level.

### Why this distinction matters — systems thinking

**Coupling and cohesion:**
- Qdrant approach: embedding logic is coupled to your application. If you have 5 services
  ingesting data, each needs to know about OpenAI, handle API keys, manage batching. But you
  have full control — different services can use different models, preprocess text differently.
- Weaviate approach: embedding is cohesive with storage. Configure once at the DB, all clients
  just send text. But now model choice is a database-level decision, not an application one.
  Changing models means reconfiguring infrastructure, not deploying code.

**The consistency guarantee:**
This is the deeper insight. When the app owns embedding (Qdrant), nothing prevents you from
accidentally embedding some data with `text-embedding-3-small` and other data with
`text-embedding-3-large` into the same collection. The DB can't enforce consistency because
it only sees opaque float arrays. We already saw this problem — mixing models produces
garbage results.

When the DB owns embedding (Weaviate), this class of bug is impossible. The vectorizer is
configured per-collection. Every object gets the same treatment. The DB enforces consistency.

**The extensibility trade-off:**
Weaviate's module system uses a sidecar architecture — the vectorizer runs as a separate
container. This is the same pattern as Envoy/Istio service mesh, Kubernetes sidecar
containers, or Postgres FDW (foreign data wrappers). The core system defines interfaces;
modules implement them in isolation.

Consequence: Weaviate deployments are heavier. Instead of one container (Qdrant), you run
Weaviate core + a vectorizer container + potentially a reranker container. Each is a failure
point. This is the classic "monolith vs microservice" trade-off applied to database internals.

**Schema vs schemaless — data modeling philosophy:**
Qdrant payloads are schemaless JSON — throw anything in, index what you need later. Like
MongoDB or early Elasticsearch. Fast to iterate, easy to evolve, but no compile-time safety.

Weaviate uses strict schemas (called "classes") — you define properties and their types
upfront. Like Postgres tables. More friction to change, but the DB validates your data and
can optimize storage. You also declare *which properties to vectorize* in the schema, giving
fine-grained control over what the embedding model sees.

**Hybrid search — why it matters for lyrics:**
Weaviate natively supports hybrid search: combining vector similarity (semantic) with BM25
keyword matching in a single query. This is interesting for lyrics because sometimes you
want semantic ("songs about heartbreak") and sometimes you want literal ("songs containing
the phrase 'dancing in the dark'"). Qdrant can do full-text search on payload fields, but
it's not fused into the vector ranking the way Weaviate does it.

### Questions to explore

- Where should the embedding boundary live in a self-hosted stack? If Ollama is already
  running as a service, does it make more sense for the DB to call it (Weaviate) or for
  the app to call it (Qdrant)?
- How does Weaviate's schema-first approach affect iteration speed when you're still figuring
  out your data model?
- Is hybrid search (vector + BM25) genuinely better for lyrics, or is pure vector search
  sufficient once the embedding model is good enough?
- How do the failure modes differ? (Qdrant: if OpenAI is down, ingestion fails in your app.
  Weaviate: if OpenAI is down, the DB itself can't accept writes.)

## Implementation Plan

### Phase 1 - Architecture Study

- [ ] Understand vectorizer module system — how modules hook into the HNSW index pipeline
- [ ] Study schema design: strict schemas vs Qdrant's schemaless payloads — implications for evolving data models
- [ ] Evaluate hybrid search (vector + BM25 keyword) — is this useful for lyrics where exact phrases matter?
- [ ] Understand multi-tenancy model — relevant if lrc-match ever supports multiple users

### Phase 2 - Comparative Ingestion

- [ ] Ingest the same lyrics dataset into Weaviate with text2vec-openai
- [ ] Run the benchmark queries from PRD-01 against both Qdrant and Weaviate
- [ ] Compare: result ranking differences, query latency, operational complexity
- [ ] Test "bring your own vectors" mode vs letting Weaviate handle embedding

### Phase 3 - Decision

- [ ] Document when Weaviate is the better choice vs Qdrant for this project
- [ ] Evaluate deployment footprint (Weaviate + module containers vs Qdrant single binary) for homelab
- [ ] Decide: adopt, keep as reference knowledge, or revisit later

## Open Questions

- Does Weaviate's built-in vectorization make chunking strategy less important? (It still processes text you give it — chunking is your responsibility)
- How does Weaviate's hybrid search (vector + BM25) compare to pure vector search for lyrics?
- Is the Docker Compose setup for Weaviate + modules practical for a homelab?
- Weaviate uses a schema (like SQL tables) vs Qdrant's schemaless payloads — which is better for evolving data models?

## References

- [Weaviate Documentation — Getting Started](https://docs.weaviate.io/weaviate)
- [Weaviate Quickstart: Locally hosted with Docker](https://docs.weaviate.io/weaviate/quickstart/local)
- [Weaviate Quickstart: Bring your own vectors](https://docs.weaviate.io/weaviate/starter-guides/custom-vectors)
- [Weaviate Concepts: Modules](https://docs.weaviate.io/weaviate/concepts/modules)
- [Weaviate Module System Architecture (contributor guide)](https://weaviate.io/developers/contributor-guide/weaviate-modules/architecture)
- [Weaviate vs Qdrant Comparison 2025 — Cipher Projects](https://cipherprojects.com/blog/posts/weaviate-vs-qdrant-vector-database-comparison-2025/)
- [Vector Database Comparison: Pinecone vs Weaviate vs Qdrant — LiquidMetal AI](https://liquidmetal.ai/casesAndBlogs/vector-comparison/)
- [Vector DB Comparison — Perivitta Rajendran](https://pr-peri.github.io/blogpost/2026/01/10/blogpost-vector-db-comparison.html)
- [Getting Started with Weaviate — Leonie Monigatti](https://www.leoniemonigatti.com/blog/weaviate-getting-started.html)
- [GitHub: weaviate/weaviate](https://github.com/weaviate/weaviate)

---

## Changelog

- 2026-03-18: Initial draft
