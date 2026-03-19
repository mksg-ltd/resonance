---
name: teaching-style-preference
description: User wants conceptual depth and explanations around vector DB / ML concepts, not just working code
type: feedback
---

User is learning vector databases and embeddings. Conceptual depth is welcome ONLY around Qdrant, vectors, and embedding concepts — explain the "why" behind things, not just the "how".

For everything else (FastAPI, config, project plumbing, Python patterns), treat as plumbing — the user knows what they're doing. Be concise, don't over-explain.

**Why:** The project is explicitly for learning vector/embedding concepts (pgvector → Qdrant progression). But the user has strong Python/Django experience and doesn't need hand-holding on web frameworks, config patterns, or project setup.

**How to apply:** When touching Qdrant, embeddings, HNSW, distance metrics, quantization, payload filtering — explain concepts as they come up. For FastAPI routes, pydantic config, pre-commit hooks, Makefile targets — just do it, skip the lecture.
