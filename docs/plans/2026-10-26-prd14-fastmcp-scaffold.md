---
status: verified
approved: true
iterations: 0
branch: spec/prd14-fastmcp-scaffold
base_branch: spec/prd13-user-search-playlist
base_commit: db678b6034dba5157f0afe552104a8f25b7a5fdf
prd: docs/prds/14-fastmcp-scaffold.md
created: 2026-10-26
updated: 2026-10-26
author: MK
tags: [mcp, fastmcp, auth]
---

# PRD-14 FastMCP Scaffold Implementation Plan

## Summary

**Goal:** Provide a mounted FastMCP HTTP endpoint that validates the same caller
sessions as FastAPI and can be exercised before user tools are added.

**Architecture:** Mount FastMCP at `/mcp/` in the existing FastAPI process. Its token
verifier uses a shared `AuthRuntime` session resolver; future tools call existing
FastAPI contracts through an in-process ASGI client. Keep MCP modules isolated; do not
create a second auth runtime or weaken the HTTP transport guard.

**Tech Stack:** FastMCP 3.x, FastAPI, uv.

## Scope

### In Scope

- FastMCP Streamable HTTP server mounted at `/mcp/` on port 8000, with the existing
  public `/health` route.
- Custom FastMCP token verifier that resolves the bearer through the same AuthRuntime
  helper used by FastAPI and rejects invalid or revoked sessions.
- Empty tool registry; verify authenticated initialize and `tools/list` only.
- FastMCP mount, shared transport guard, and operator docs.

### Out of Scope

- Search, collection, lyric, playlist, resource, or prompt components.
- MCP OAuth authorization server, consent/login UI, dynamic client registration, or
  token refresh. Clients manually supply a token issued by `/api/auth/token` in this
  initial scaffold; validate this with a real target client before tools work begins.
- FastAPI or Navidrome business policy changes; direct Navidrome calls; CLI subprocesses.

## Prerequisites

- PRD-12 auth foundation and bearer JWT issuance are available on the base branch.
- FastAPI remains one worker because its Navidrome sessions and signing key are process-local.
- User has an account accepted by Navidrome and can obtain a bearer via
  `POST /api/auth/token` over trusted local development or HTTPS.

## Context for Implementer

- **Patterns:** `src/resonance/routes/auth.py` validates bearer tokens and active
  sessions. `src/resonance/app.py` creates the API. Nool's `nool_mcp/server.py` and
  `homelab/obsidian-mcp/python-trial-src/server.py` show FastMCP construction,
  `http_app`, health routes, and tool registration. Do not copy their user/OAuth stores.
- **Conventions:** `Settings` use Pydantic settings with `RESONANCE__` prefix;
  dependency and app mounting patterns are in `pyproject.toml` and `src/resonance/app.py`.
  Never log bearer headers or credentials.
- **Key files:** `.gitignore`, `pyproject.toml`, `uv.lock`, new
  `src/resonance/mcp/{__init__,auth,server}.py`, `src/resonance/app.py`,
  `src/resonance/routes/auth.py`, `README.md`, and new MCP tests.
- **Gotchas:** The API signs JWTs with a process-local random secret and keeps active
  upstream sessions in memory. MCP must use a shared AuthRuntime token/session
  resolver; do not copy secrets or add an auth database. FastMCP's token verifier gets
  only the token, so apply the existing HTTPS/local-development transport policy in
  parent FastAPI request middleware on `/mcp/`. Compose FastMCP's `http_app` lifespan
  explicitly with FastAPI's existing Qdrant/session lifespan; a mounted ASGI app's
  lifespan is not automatically entered by Starlette.
- **Domain context:** The token endpoint is for non-browser callers. The Vue browser
  continues using its HttpOnly cookie. A later MCP tool should pass bearer auth to
  FastAPI and let its routes enforce per-library access.
- **Artifact directory:** `/tmp/resonance-prd14-fastmcp-artifacts`
- **Test framework constraints:** Python pytest and FastAPI TestClient are available.
  Use FastMCP Client in tests and generate sessions directly. No live Navidrome account
  is needed for this scaffold.

## Runtime Environment

- **Start command:** `make run` starts FastAPI and its mounted FastMCP endpoint.
- **Port:** API and MCP share port 8000; MCP path is `/mcp/`.
- **Deploy path:** Existing `resonance` image and Compose service.
- **Health check:** `GET http://127.0.0.1:8000/health` returns `200`.
- **Restart procedure:** Restart the existing API process after MCP changes; auth
  behavior and active sessions follow the existing API lifecycle.
- **Code identity:** Connect an authenticated FastMCP Client to
  `http://127.0.0.1:8000/mcp/` and list the empty tool set.

## Feature Inventory

No existing MCP code is replaced. Existing authenticated FastAPI contracts remain the
source of truth and are consumed by future MCP tools. No CLI or Vue behavior changes.
Track `src/resonance/data/embedding_profiles.yaml` and narrow the root `data/` ignore
pattern: `pyproject.toml` force-includes this required catalog, but the broad existing
ignore rule excluded it from clean checkouts and prevented editable package builds.

## Progress Tracking

- [x] Task 1: Add FastMCP package and the bearer-verifying protocol server.
- [x] Task 2: Mount MCP and preserve transport security.
- [x] Task 3: Verify client protocol and document boundaries.

**Total Tasks:** 3 | **Completed:** 3 | **Remaining:** 0

## Implementation Tasks

### Task 1: FastMCP server and shared bearer validation

**Objective:** Create a FastMCP server factory that validates caller tokens with the
existing FastAPI runtime and exposes no application tools yet.

**Dependencies:** None

**Files:**

- Create: `src/resonance/mcp/__init__.py`, `src/resonance/mcp/auth.py`,
  `src/resonance/mcp/server.py`
- Modify: `.gitignore`, `pyproject.toml`, `uv.lock`, `src/resonance/auth.py`,
  `src/resonance/routes/auth.py`, `src/resonance/app.py`
- Add: `src/resonance/data/embedding_profiles.yaml` (required bundled package data
  currently omitted by the broad ignore rule)
- Test: `tests/test_mcp_auth.py`, `tests/test_mcp_server.py`

**Key Decisions / Notes:**

- Use FastMCP's `TokenVerifier` extension point and a shared AuthRuntime method that
  validates token signature, expiry, active session, and subject. Do not subclass or
  copy Nool/Obsidian OAuth authorization servers, because FastAPI already issues the
  bearer JWT.
- Convert only active Resonance sessions into FastMCP access-token context. Reject
  empty/malformed bearer values and expired/revoked sessions.
- Apply the existing bearer transport requirements to `/mcp/`: loopback HTTP only in
  debug mode and HTTPS for remote use. Reject browser-cookie auth for MCP.
- Register no tools, resources, or prompts. Existing `/health` remains public.

**Definition of Done:**

- [x] Valid active Resonance bearer authenticates an MCP initialize and empty
      `tools/list` response.
- [x] Missing/invalid/revoked bearer does not authenticate.
- [x] Identity comes from the shared server-side session; MCP never trusts a username
      in client input.

**Verify:**

- `uv run pytest tests/test_mcp_auth.py tests/test_mcp_server.py -q` — auth and MCP
  transport tests pass.

### Task 2: Mount MCP and preserve transport security

**Objective:** Mount the FastMCP ASGI app in FastAPI and apply the same secure transport
policy as existing bearer-protected routes.

**Dependencies:** Task 1

**Files:**

- Modify: `src/resonance/app.py`, `src/resonance/routes/auth.py`, `README.md`
- Test: `tests/test_mcp_server.py`, auth transport tests as needed

**Key Decisions / Notes:**

- Mount the FastMCP ASGI app at `/mcp/`; parent API lifespan owns its lifecycle.
- Enter the FastMCP HTTP app lifespan explicitly inside the existing FastAPI lifespan
  (preserving Qdrant setup and auth-session cleanup).
- Apply the shared bearer transport guard in root middleware for `/mcp/` paths before
  FastMCP processes requests; the verifier cannot inspect scheme/host itself.
- Reuse the existing `/health` route; do not add another port, service, secret, or auth
  configuration.
- Document how to obtain a user token, configure FastMCP Client with bearer auth, and
  interpret the empty tool list as an intentional scaffold.

**Definition of Done:**

- [x] `make run` and the normal Compose stack serve the mounted MCP endpoint in the
      existing FastAPI process; `/health` continues to respond.
- [x] Existing transport protections apply to `/mcp/`, rejecting bearer requests over
      remote plain HTTP.
- [x] FastMCP startup and shutdown run alongside existing FastAPI/Qdrant startup and
      cleanup without leaking its session manager.

**Verify:**

- `make run` plus `/health` and authenticated MCP Client smoke — routes are available
  from the same process.
- `docker compose build resonance` — image includes FastMCP and the mounted server.

### Task 3: Verify client protocol and document boundaries

**Objective:** Prove the scaffold handles authenticated MCP protocol traffic and remains
an empty adapter without changing product behavior.

**Dependencies:** Tasks 1–2

**Files:**

- Modify: `README.md`, PRD-14 plan evidence
- Test: MCP ASGI/HTTP tests

**Key Decisions / Notes:**

- Exercise authenticated `initialize`, `tools/list`, existing health, unauthorized
  requests, logout/revocation, and transport restrictions. Use generated in-memory
  sessions in automated tests.
- Manual smoke uses `fastmcp.Client` with a bearer token from `/api/auth/token`; no
  third-party OAuth auto-configuration is claimed. Document the exact client snippet.
- No need to run Navidrome or Qdrant for this scaffold test.

Example after exporting a short-lived token as `RESONANCE_MCP_TOKEN`:

```python
import asyncio
import os

from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

transport = StreamableHttpTransport(
    url="http://127.0.0.1:8000/mcp/",
    headers={"Authorization": f"Bearer {os.environ['RESONANCE_MCP_TOKEN']}"},
)

async def main():
    async with Client(transport) as client:
        assert await client.list_tools() == []
        print("Authenticated; no user tools are registered yet.")

asyncio.run(main())
```

**Definition of Done:**

- [x] Automated tests verify valid-token protocol operation and closed failure cases.
- [x] Packaged server starts and `/health` responds according to Qdrant availability.
- [x] Documentation says there are no tools yet and records the manual bearer-token
      limitation for this increment.

**Verify:**

- `uv run pytest tests/test_mcp_auth.py tests/test_mcp_server.py -q`.
- `docker compose build resonance` and a temporary packaged `/mcp/` protocol smoke.
- `git diff --check`.

**Completed evidence (2026-10-26):** `uv run pytest -q` — 107 passed, 4 warnings;
`uv run ruff check src/`, `uv run ruff format --check src/`, `uv run ty check src/`,
and `git diff --check` passed. `docker compose build resonance` succeeded. The
packaged container started; without a Qdrant endpoint its `/health` correctly returned
503 (`qdrant: unreachable`), and a remote plain-HTTP `/mcp/` request returned 400
(`HTTPS is required`). FastMCP authenticated initialize and empty `tools/list`,
revocation, missing credentials, and transport policy are exercised by the automated
ASGI tests. The bundled embedding-profile catalog was added because a broad `.gitignore`
rule had excluded this package data required by clean builds.

## Testing Strategy

- Unit: verifier resolves valid sessions through shared AuthRuntime and rejects invalid
  and revoked tokens.
- Integration: MCP client initializes, lists zero tools with a verified bearer, and
  fails without valid credentials.
- Runtime: mounted ASGI lifespan, existing health route, and shared AuthRuntime.
- Regression: existing Python suite remains green; no FastAPI application routes change.

## Risks and Mitigations

| Risk                                                                | Likelihood | Impact | Concrete mitigation                                                                                                                 |
| ------------------------------------------------------------------- | ---------- | ------ | ----------------------------------------------------------------------------------------------------------------------------------- |
| MCP and FastAPI diverge on session validity                         | Low        | High   | Resolve token through a single shared AuthRuntime method used by API dependencies and FastMCP.                                      |
| MCP credentials leak through proxy logs                             | Med        | High   | Never log request headers or token contents; require HTTPS outside loopback debug mode.                                             |
| Target clients require automatic OAuth instead of configured bearer | Med        | Med    | Keep this scaffold tool-free; test one target client and design OAuth before exposing tools if bearer configuration is unsupported. |
| Plain HTTP bypasses bearer transport protections                    | Low        | High   | Apply the API transport guard to `/mcp/` and test loopback, HTTPS, and remote HTTP cases.                                           |

## Removes

- None.

### Removes (verify)

- None.

## ADR Reference

No ADR needed. FastMCP is an adapter over existing FastAPI contracts; no core application
abstraction is replaced.

## Open Questions

- Which external MCP client should be the first interoperability target? The scaffold
  can be validated with FastMCP Client or MCP Inspector; automatic OAuth onboarding is
  deferred until a client is selected.

### Deferred Ideas

- Search/review and playlist MCP tools, after Vue match-quality validation and the
  authenticated scaffold is exercised.
- OAuth 2.1 authorization server or another credential acquisition flow if target MCP
  clients cannot use the existing short-lived bearer token.
- MCP prompts/resources and seed-song or assistant-composed playlist workflows.
