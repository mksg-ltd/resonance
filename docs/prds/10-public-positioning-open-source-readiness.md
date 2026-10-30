---
status: in-progress
author: strand
tags: [open-source, self-hosted, v1, security, licensing, release-readiness]
title: "Open-Source and Self-Hosted Readiness"
phase: launch
created: 2026-10-23
updated: 2026-10-30
---

# Open-Source and Self-Hosted Readiness

## Summary

Resonance is a self-hosted semantic music discovery service for Navidrome. Before
calling it a v1 or recommending it to people outside the maintainer's own setup, a
new operator must be able to understand what it does, install it, secure its network
boundary, choose local or hosted embeddings with informed consent, preserve or remove
its data, and identify the project's license and support limits.

This PRD defines the product and release requirements for that readiness work. It
does not announce a release, certify legal compliance, or authorize implementation by
itself. It does not assume that a project license, model license, or right to process
lyrics also grants a right to redistribute those materials.

**Target:** a clearly scoped, responsibly distributable v1 for technically capable
self-hosters running one Navidrome server. The initial supported installation is
Docker Compose on a maintainer-approved platform. Access is local by default; remote
use requires a documented TLS-terminating proxy and a configured trusted-proxy
boundary.

## User and Product Context

### Primary user

A listener or household operator runs Navidrome and owns or is otherwise authorized to
use the music library. The operator installs Resonance, configures an embedding
profile, selects an accessible Navidrome library, and ingests it. A listener signs in
with their own Navidrome credentials, searches by lyric meaning, reviews excerpts, and
chooses whether to save a private playlist to their Navidrome account.

### Product promise

Resonance finds candidate songs by semantic similarity between a text query and
sections of synced lyrics. It makes matches reviewable by showing lyric excerpts. It
does not determine whether a song is objectively about a theme, analyze audio,
generate playback, or guarantee relevance across languages or libraries.

### Current product baseline

The following are codebase observations as of 2026-10-30, not readiness claims:

- Navidrome supplies library IDs, track metadata, and structured lyrics through its
  Subsonic-compatible API. Resonance does not need a mounted music directory.
- The shared application layer is called by CLI and FastAPI adapters. The Vue UI uses
  the same-origin API. A tool-free FastMCP transport scaffold exists; user-facing MCP
  tools are a separate feature and are not part of this PRD.
- Users authenticate with Navidrome credentials. Resonance keeps bounded sessions and
  those credentials in process memory, issues process-signed tokens, and expires
  sessions after 12 hours. Restarting Resonance clears sessions and invalidates tokens.
  The exact configured Navidrome username in `RESONANCE_ADMIN_USER` receives admin
  capabilities; there is no separate Resonance role database.
- Collection visibility is checked against the caller's currently accessible
  Navidrome libraries. Ingestion and collection deletion require the configured admin
  username. Playlist creation verifies library membership and confirms the saved
  playlist's owner, privacy, contents, and order.
- Lyrics sections and metadata are stored in Qdrant. The playlist-save journal is
  stored in SQLite. Qdrant writes can resume when the same collection settings and
  source content are unchanged. Full refresh, changed-lyric replacement, and removal
  of tracks deleted from Navidrome are not implemented.
- Embedding profiles select a model and protocol. TEI and Ollama may run locally;
  OpenAI-compatible profiles can target a local or hosted endpoint. The destination
  and provider terms depend on operator configuration.
- Compose currently binds Resonance, Qdrant, and TEI host ports to loopback and disables
  interactive API docs. It enables Resonance debug mode for local sign-in and uses
  floating Qdrant/TEI/uv image references. These are local development defaults, not a
  hardened public deployment profile.
- AGPL-3.0-only has been selected, the canonical license text is tracked in the root
  `LICENSE`, and the Python package metadata declares the same identifier. There is no
  published release artifact license inventory or SBOM.
  The checked-in Python and frontend lockfiles provide dependency versions, but no
  release artifact license inventory or SBOM is currently maintained.

This baseline replaces the stale pre-Navidrome assumptions in earlier drafts. The
retired filesystem scanner, request-selected `data_dir`, forced local M3U writes,
Mutagen dependency, and unauthenticated playlist mutation routes are not current
product behavior and must not be treated as open issues in this PRD.

## Goals

- Define the v1 audience, supported deployment boundary, supported features, and
  limitations in language that matches the running product.
- Make the repository's code license, third-party software notices, container
  contents, model dependencies, and lyrics handling explicit before distribution.
- Make the default installation safe for a local self-hosted instance and give
  operators a verifiable path to configure remote HTTPS access.
- Explain authentication, authorization, network access, data flows, persistence,
  backups, deletion, recovery, and failure behavior in operator-facing documentation.
- Verify that the documented boundaries hold through focused automated checks and a
  clean-install acceptance run.
- Establish sustainable v1 support, upgrade, vulnerability-reporting, and release
  practices without implying enterprise support or production guarantees.

## Non-Goals

- Hosted Resonance service, SaaS tenancy, public multi-tenant deployment, or an
  enterprise role/identity system.
- Replacing Navidrome authentication, shipping passwords in configuration, or
  introducing a Resonance user database.
- Playback, Jellyfin support, general playlist editing/deletion, automatic playlist
  generation, MCP tool design, or conversational assistant UX. These are covered by
  other product work, if pursued.
- Full per-library refresh, changed-lyric reconciliation, automatic Qdrant pruning,
  or durable ingestion-job recovery across process restarts.
- Shipping or publishing a user's lyrics, audio, private Qdrant collection, model
  weights, or production library as sample data.
- Providing a legal opinion or treating a software license scan as legal clearance.
- Claiming universal multilingual quality, objective thematic classification,
  competitor superiority, or exclusive semantic-playlist capability.

## Functional Requirements

### R1. Product and support definition

The release documentation MUST state:

- the primary user, required Navidrome server, and supported single-instance
  deployment shape;
- the distinction between admin ingestion and listener search/playlist actions;
- supported embedding protocols and the operator responsibility for the selected
  model and endpoint;
- what is available in v1 and what is not, including no playback, no full refresh,
  and no production MCP tools unless their separate PRD is completed;
- tested software/platform versions and resource expectations, or an explicit
  experimental label when a platform has not been tested;
- the support level, upgrade policy, and a project contact path for defects and
  security reports.

Claims MUST distinguish implemented, tested, planned, and unsupported behavior.

### R2. License and distribution inventory

Before publishing an installable release, maintainers MUST:

- approve the project's license and copyright/ownership statement, add the tracked
  license text, and make package metadata, repository documentation, and release
  artifacts agree;
- inventory direct and transitive Python and frontend dependencies, bundled assets,
  container base/runtime images, and build tools for each distributed artifact;
- retain license evidence and required notices for the versions actually shipped;
- generate and retain a software bill of materials for the source/package and
  container release, or record an explicit reason and an owner-approved alternative;
- document unresolved obligations and exclude affected material or block the
  affected artifact until an authorized maintainer resolves them.

The inventory MUST cover the current stack; previous Mutagen-specific concerns are
obsolete unless that dependency is deliberately reintroduced.

### R3. Model and lyrics rights/data handling

The product MUST explain separately:

- that model/profile metadata in Resonance does not grant rights to model weights;
- which model artifact/revision is pulled by a local runtime and the operator's role
  in reviewing its license and terms;
- that selecting a hosted embedding endpoint sends lyric text, and semantic-search
  query text, to that configured service;
- that synced lyrics and section payloads are stored in the operator's Qdrant
  instance, while playlist operation records are stored in the SQLite journal;
- that Resonance does not include a production lyrics corpus or grant rights to
  redistribute lyrics obtained through Navidrome;
- how to delete a collection, preserve/restore persistent data, and remove all
  Resonance state when uninstalling.

Release materials, test fixtures, screenshots, example logs, and demo collections
MUST contain only original, synthetic, or explicitly cleared content. The release
must not imply that private library access authorizes public redistribution.

### R4. Secure-by-default deployment

The supported Compose deployment MUST:

- expose Resonance only on loopback by default;
- keep Qdrant and embedding-runtime ports on the private Compose network unless an
  operator explicitly opts into a host binding, with loopback-only examples for
  local debugging;
- disable debug mode, automatic reload, and interactive API documentation by
  default in the production profile;
- avoid floating image tags for the application runtime, Qdrant, embedding runtime,
  and build tools in a release; identify the model revision or explain the runtime
  limitation if its source cannot pin one;
- use non-root application execution, preserve writable state in named volumes, and
  avoid granting the application write access to the Navidrome music library;
- provide a sample environment file with placeholders only and clear instructions
  for protecting the real `.env` file and backups.

Remote access instructions MUST require HTTPS termination, exact trusted proxy
addresses, preservation of the accepted public `Host`, rejection of unknown hosts,
and safe forwarded-header handling. Plain remote HTTP MUST be documented as
unsupported. Direct access to Qdrant or embedding-runtime ports MUST be treated as
an administrative network boundary, not protected by Resonance login.

### R5. Authentication and authorization boundary

The service MUST preserve Navidrome-backed identity and enforce authorization at the
API boundary:

- unauthenticated callers cannot use protected APIs or mutate playlists,
  collections, or ingestion state;
- a caller can see and search only collections bound to libraries currently
  accessible to that Navidrome account;
- playlist saves contain only current library song IDs and are private to the
  authenticated Navidrome user;
- admin-only actions require the configured admin username, including ingestion,
  collection deletion, and library enumeration where currently required;
- cookie-authenticated mutations enforce the documented same-origin/Origin policy;
- authentication errors, logs, and configuration endpoints do not reveal passwords,
  bearer tokens, session cookies, API keys, or full lyric text.

Regression checks MUST cover at least two Navidrome users with different library
access, the configured admin and a non-admin, cookie and bearer authentication, and
direct attempts to reach backend services outside the documented boundary. No admin
privileges may be inferred from a user-supplied request field.

### R6. Data lifecycle, recovery, and operational diagnostics

Operator documentation MUST identify each persistent store and its content:

- Qdrant collections: lyrics sections, metadata, embedding/profile/index metadata;
- SQLite journal: playlist-save request and outcome data, not track-to-file mapping;
- Compose volumes/caches: Qdrant state, playlist journal, and any locally downloaded
  model data.

It MUST explain backup/restore, collection deletion, whole-instance removal, and the
fact that session and in-memory ingestion-job state is lost on service restart. It
MUST explain that completed Qdrant writes remain after a failed/stopped job and that
repeating the same ingestion against the same collection can reuse verified complete
tracks but does not provide full refresh semantics.

Logs MUST identify operation/job, stage, target library/collection where safe,
aggregate progress, and actionable failure category. Default logs MUST omit
credentials, tokens, complete lyrics, and raw upstream bodies. The health endpoint,
container logs, and restart/retry path MUST be documented and exercised.

### R7. Installation and upgrade experience

A new operator MUST be able to follow a clean-machine Compose guide that covers:

- prerequisites and verified platform/architecture;
- creating and protecting `.env`, configuring Navidrome, the admin username, Qdrant,
  and a local or hosted embedding profile;
- starting, checking, updating, backing up, restoring, and stopping the services;
- logging in with a Navidrome account, choosing an accessible library, creating an
  initial collection, searching, and saving/verifying a private playlist;
- interpreting skipped tracks, failed ingestion logs, and resumable/partial writes;
- the different privacy/data flow when using a hosted embedding endpoint.

The guide MUST not require a source-code checkout or editing bundled frontend code
for the supported Compose installation. Upgrade steps MUST state which data formats
and persistent volumes are preserved and what rollback is possible.

### R8. Release and maintenance practices

Each v1 release MUST have a versioned changelog/release note, pinned source and
container inputs, build provenance sufficient to identify the shipped code, license
notices/SBOM, and a recorded smoke check for the supported installation. The project
MUST describe how to report vulnerabilities privately, how maintainers handle
security reports, which versions receive fixes, and that self-hosters remain
responsible for backups, network exposure, Navidrome, Qdrant, and model-provider
availability.

## Quality and Acceptance Criteria

The v1 readiness gate is met only when all required evidence below is recorded:

1. **Product claims:** README and install guide describe only behavior verified in
   current code. They label future refresh and MCP tool behavior as deferred and make
   no unverified quality, exclusivity, legal-clearance, or privacy guarantees.
2. **License:** maintainers approve a project license; tracked license and package
   metadata agree; software inventories, notices, model references, and shipped
   artifacts are reviewed with no unresolved blocker hidden from users.
3. **Deployment boundary:** a clean Compose config exposes only the documented
   listener ports. Qdrant and inference ports are unreachable from other hosts by
   default. Production docs/API settings have debug and interactive docs off. Remote
   HTTPS proxy configuration is verified with its exact trusted peer and host policy.
4. **Authorization:** automated route tests demonstrate isolation between two users
   with different Navidrome libraries, admin-only operations, private playlist
   ownership, cookie Origin checks, and bearer scope. Denied requests create no
   collection, playlist, or ingestion side effects.
5. **Data flows:** docs enumerate destinations and content sent to Navidrome, Qdrant,
   local embedding runtime, and hosted embedding providers. A canary review confirms
   no secrets or full lyric bodies appear in default logs, errors, or release files.
6. **Lifecycle:** a maintainer completes documented backup and restore, collection
   deletion, whole-instance removal, and restart during/after ingestion without
   losing verified writes or misrepresenting job/session continuity.
7. **Onboarding:** a person other than the original author follows the clean install
   guide on a listed platform and completes login, initial indexing, search, and
   private playlist verification without undocumented edits.
8. **Release evidence:** source and container versions are pinned, a release artifact
   can be traced to its source revision, the SBOM/notices are attached or linked, and
   supported-platform smoke checks are recorded.
9. **Support posture:** a security contact and supported-version policy are
   published; release copy distinguishes a tested self-hosted v1 from a guaranteed
   production service.

## Prioritization

### Required before calling the product v1-ready

- Decide project licensing and resolve distribution obligations for software,
  container contents, and bundled assets.
- Replace development Compose defaults with the secure supported profile and pin
  release inputs.
- Complete authorization/network-boundary verification and publish the data-flow,
  privacy, backup, recovery, and clean-install guidance.
- Demonstrate a clean install and end-to-end Navidrome workflow on the supported
  platform, then record release evidence and maintenance/support scope.

### Follow-up after the first responsible public release

- Broader OS/architecture support and installation methods beyond Docker Compose.
- Automated dependency/model update policy and richer release provenance.
- Durable ingestion jobs, full per-library refresh, and automated removal/reindex of
  changed or deleted Navidrome tracks.
- Production MCP tools, playback integrations, and assistant-driven playlist flows.
- Performance and semantic-quality benchmarks on a rights-cleared multilingual test
  corpus.

## Open Decisions

These are product-owner or maintainer decisions. They should be resolved while
shaping this PRD, before a later implementation spec is approved.

1. **Project license and ownership:** AGPL-3.0-only is selected and its text and Python
   metadata are present. Confirm copyright ownership and release approval authority,
   and decide whether distribution includes source, Python package, container image, or
   all three.
2. **Supported platform:** Which host OS and CPU architectures will be tested for the
   v1 Compose install? Is a local CPU embedding profile the minimum supported path?
3. **Network exposure:** Is loopback-only Compose the supported default, with remote
   use only through an operator-provided HTTPS proxy? Is LAN HTTP explicitly
   unsupported?
4. **Data lifecycle:** Which operator action should remove a Qdrant collection, and
   should whole-instance deletion preserve or remove the playlist journal by
   default? What exact backup/restore guarantee is expected?
5. **Model/provider list:** Which profiles are actively supported at v1, and who
   verifies upstream model/weight terms when profile revisions change?
6. **Support promise:** Is the first release experimental/self-supported, or will
   maintainers commit to a response/update window and supported release lifetime?
7. **External security contact:** Which public address or repository mechanism will
   receive vulnerability reports?

## References

- [PRD-12 — Authentication foundation](12-auth-foundation.md)
- [PRD-13 — Assistant user experience and Vue client](13-assistant-user-experience.md)
- [PRD-14 — FastMCP scaffold](14-fastmcp-scaffold.md)
- [PRD-15 — Admin ingestion jobs](15-admin-ingestion-jobs.md)
- [Operator and API documentation](../../README.md)
- [Compose deployment](../../docker-compose.yml)
- [Python dependency manifest and lock](../../pyproject.toml)
- [Embedding profile catalog](../../src/resonance/data/embedding_profiles.yaml)

## Changelog

- 2026-10-23: Initial draft focused on broad positioning and pre-Navidrome risks.
- 2026-10-30: Reconciled with the current Navidrome-backed product; replaced stale
  filesystem/M3U/Mutagen assumptions with v1 audience, trust boundary, data handling,
  distribution, installation, recovery, and release requirements.
- 2026-10-30: Maintainer selected AGPL-3.0-only and added the canonical license text.
  README, package metadata, contributor guidance, installation guide, and project
  document index identify the license. Ownership confirmation and distribution review
  remain release gates.
