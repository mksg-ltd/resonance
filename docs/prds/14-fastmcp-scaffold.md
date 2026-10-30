---
status: completed
author: MK
tags: [mcp, fastmcp, auth, navidrome, scaffold-complete, no-user-tools-yet]
title: "PRD-14: FastMCP Server Scaffold"
phase: foundation
created: 2026-10-26
updated: 2026-10-27
---

# PRD-14: FastMCP Server Scaffold

**Status**: Completed as an isolated scaffold increment after the Vue
search/review/playlist work in [PRD-13](13-assistant-user-experience.md). The search
and playlist MCP tools remain deferred; the scaffold has no user-facing tools.

## Purpose

Add a small FastMCP HTTP server to Resonance that establishes the deployment,
transport, and authentication boundary for later user-facing MCP tools. It must reuse
Resonance's existing Navidrome-verified user identity and FastAPI authorization; it
must not introduce another account store or copy the business logic exposed to Vue.

## Problem

Resonance's user workflows are exposed through authenticated FastAPI routes and the
Vue application. MCP is the planned interface for LLM clients, but the project has no
MCP server yet. A minimal server gives us a place to validate FastMCP lifecycle, shared
user authentication, and the same user's short-lived Resonance bearer token before we
expose lyric search or playlist creation to a model.

## Goals

- Add a FastMCP HTTP endpoint mounted at `/mcp/` in the existing FastAPI process.
- Keep FastMCP as a thin protocol adapter. Future tools call the same FastAPI
  contracts as Vue; they do not spawn CLI subprocesses, call Navidrome directly, or
  duplicate application policy.
- Validate each caller's Resonance bearer token through the same runtime/session store
  used by FastAPI before serving protected MCP requests. FastAPI remains authoritative
  for token expiry, logout/revocation, Navidrome identity, and library permissions.
- Use the token returned by `POST /api/auth/token`. The token is passed as a bearer
  header by the MCP client; the MCP server never asks for or stores the Navidrome
  password.
- Provide an HTTP health route and a minimal protocol surface that can be exercised
  by a FastMCP client or MCP Inspector.
- Keep the scaffold isolated from Vue and the existing `/api` route behavior.

## Non-Goals

- Search, collection discovery, lyric reading, playlist creation, playlist status, or
  any other user-facing tools, resources, or prompts. These will be specified after
  this scaffold is exercised.
- A new Resonance OAuth 2.1 authorization server, interactive MCP login/consent page,
  token refresh flow, account linking, or separate OAuth/role database. MCP clients
  must accept a user-provided bearer token for this first scaffold. If target clients
  require OAuth discovery or a browser-based flow, that will be a separate auth design
  before user tools are exposed.
- Admin ingestion/configuration tools, playback, stdio transport, or public access.
- Changes to Navidrome authentication or the FastAPI authorization policy in PRD-12.

## User and System Flow

1. A user obtains a short-lived Resonance bearer token through the existing
   `POST /api/auth/token` endpoint using their own Navidrome username/password.
2. The MCP client connects to the configured Resonance MCP HTTP URL and sends that
   token in `Authorization: Bearer ...`.
3. FastMCP's token verifier uses the same `AuthRuntime` token/session resolution helper
   as FastAPI. It does not trust a username supplied by the client.
4. FastAPI and FastMCP validate signature, expiration, active session, and identity
   through the shared runtime. Missing, invalid, expired, or revoked credentials must
   not be treated as anonymous success.
5. For this scaffold, the MCP protocol reports no user tools. Later MCP tools will
   forward the caller's bearer token to the corresponding FastAPI endpoints, where
   library and playlist authorization remains enforced.

## Architecture Decision

Mount FastMCP's ASGI app under `/mcp/` in the existing FastAPI process. FastAPI keeps its
JWT signing key and active Navidrome sessions in process memory, and its bearer
transport guard intentionally rejects plain HTTP requests to Compose service names. A
separate MCP container calling the API over Compose HTTP would fail validation or
require weakening the transport boundary. The mounted FastMCP token verifier reuses the
same `AuthRuntime` token/session resolution as FastAPI, and `/mcp/` applies the same
HTTPS/local-development transport policy through request middleware (the FastMCP token
verifier itself receives only a token string). Compose FastMCP's HTTP app lifespan
with FastAPI's existing Qdrant/session lifespan. This avoids a second auth runtime and
an internal service secret. Later tools will use the existing FastAPI HTTP contracts
through an in-process ASGI client; no route or application policy is copied.

Use FastMCP's token-verification extension point rather than copying Nool's Django
OAuth provider or Obsidian's SQLite-backed personal-token OAuth server. Those projects
are references for FastMCP server construction, `http_app`, health routes, tool
registration, and transport tests. Their identity stores and login flows do not match
Resonance's Navidrome-backed accounts. The current scaffold uses a manually supplied
Resonance bearer token; OAuth discovery and automatic login are explicitly deferred.

## Runtime and Configuration

- Local and Docker API: `make run` or the normal Compose stack serves FastAPI and MCP
  together at `http://127.0.0.1:8000` in local development.
- MCP endpoint: `http://127.0.0.1:8000/mcp/`; the existing health check remains
  `http://127.0.0.1:8000/health`.
- Production access uses the existing HTTPS reverse proxy and the same transport
  protections as FastAPI. No separate MCP port or `.env` credential is introduced.
- Do not log authorization headers or token contents. HTTP transport is for local
  development only without TLS; remote access must be protected by HTTPS.

## Acceptance Criteria

- A FastMCP client can initialize against `/mcp/` and list an empty tool set using a
  valid token from `/api/auth/token`.
- Missing, malformed, expired, logged-out, or otherwise invalid bearer tokens are
  rejected by the shared runtime.
- The verifier does not accept client-supplied usernames or library IDs as identity
  claims.
- `/health` returns `200` without requiring a user token and exposes no account data.
- `make run` and `docker compose up --build` serve the mounted MCP endpoint with FastAPI.
- Logs, process environment, and persisted state do not contain Navidrome passwords or
  copied bearer tokens.
- No application search/save behavior changes, and no user-facing MCP tool is
  registered in this scaffold.

## References

- [PRD-12 — User Authentication and Authorization Foundation](12-auth-foundation.md)
- [PRD-13 — Assistant User Experience](13-assistant-user-experience.md)
- Local reference: `/var/home/mk/dev/mksg/nool/nool_mcp/server.py` — FastMCP
  construction, auth-provider wiring, custom health route, and HTTP app export.
- Local reference:
  `/var/home/mk/dev/mk/homelab/obsidian-mcp/python-trial-src/server.py` — standalone
  server wiring, bearer auth provider, routes, and `http_app`.
- [FastMCP authentication providers](https://gofastmcp.com/python-sdk/fastmcp-server-auth-auth)
- [FastMCP JWT token verifiers](https://gofastmcp.com/python-sdk/fastmcp-server-auth-providers-jwt)
