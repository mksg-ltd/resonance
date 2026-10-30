---
status: in-progress
author: strand
tags:
  [
    positioning,
    open-source,
    licensing,
    security,
    release-readiness,
    draft-scope,
  ]
title: "Public Positioning and Open-Source Readiness"
phase: launch
created: 2026-10-23
updated: 2026-10-27
---

# Public Positioning and Open-Source Readiness

**Status**: In progress at the PRD-scoping stage. This remains a draft and is not an
implementation approval; the release decisions and evidence gates are still open.

---

## Overview

Define what Resonance can truthfully present to the public and the licensing,
security, and deployment gates needed before recommending it for broader use.
The product's center is **semantic lyric meaning at song-section level**, not a
new label for generic AI playlists. This PRD covers the whole product; the proposed
Navidrome workflow has its own [draft PRD](09-navidrome-semantic-playlists.md).

This is a review proposal, not a promise to implement every control, publish now,
change the license, or certify the service as production-ready. No source code,
existing M3U behavior, license file, or public-facing copy changes are authorized
by creating this draft.

## Goals

- Separate implemented capability, planned capability, and unsupported marketing claims.
- Decide code/dependency licensing before claiming a distributable MIT product.
- Audit model weights and lyrics rights separately from software licenses.
- Establish a defensible minimum trust boundary and portable self-hosted setup.
- Make release blockers, decisions, and evidence-based acceptance explicit.

## Non-Goals

- Writing a launch announcement, changing README now, or creating release artifacts.
- An exhaustive legal opinion or a claim that a dependency declaration settles all
  licensing questions for every deployment/distribution arrangement.
- Enterprise multi-tenancy, hosted SaaS, adding audio analysis, or feature parity
  with another music product.
- Shipping a lyrics corpus, redistributing commercial recordings, or assuming private
  ingestion grants rights to publish lyrics, excerpts, vectors, or model weights.
- Disabling or rewriting existing M3U support as part of this documentation task.

## Current State: Facts and Limits

Repository evidence checked on 2026-10-23:

- **Missing license grant:** [README](../../README.md) says MIT, but the tracked-file
  inventory contains no LICENSE/COPYING file. A README label is not a complete
  distribution/compliance decision.
- **Mutagen:** [pyproject.toml](../../pyproject.toml) declares it directly,
  [scanner](../../src/resonance/scanner.py) imports it, and the
  [lockfile](../../uv.lock) resolves 1.47.0. Installed/package metadata declares
  `GPL-2.0-or-later`; compatibility and distribution obligations need a decision.
- **Semantic retrieval:** [chunker](../../src/resonance/chunker.py),
  [ingestion](../../src/resonance/routes/ingest.py), and
  [search](../../src/resonance/routes/search.py) implement section-level retrieval.
  No comparative benchmark or universal language-quality guarantee was verified.
- **Providers:** the [embedder factory](../../src/resonance/embedders/__init__.py)
  supports local and hosted adapters. A runtime does not establish weight licenses.
- **Unprotected mutations:** [app](../../src/resonance/app.py),
  [playlist](../../src/resonance/routes/playlists.py),
  [ingest](../../src/resonance/routes/ingest.py), and
  [collection](../../src/resonance/routes/collections.py) routes have no inspected
  application authentication/authorization guard for playlist writes or collection
  mutations. Network exposure depends on deployment; no live exploit was attempted.
- **Request-selected roots:** `PlaylistRequest.data_dir` selects a write root;
  `IngestRequest.data_dir` selects a scan root, and `force` can replace a collection.
- **Track paths:** the playlist route interpolates submitted paths into M3U entries
  without containment/control-character validation. The name sanitizer does not
  validate tracks; impact depends on the client and filesystem access.
- **UI origin:** [UI](../../ui/index.html) uses `http://localhost:8000`. A remote
  browser targets its own machine; HTTPS/reverse-proxy use also needs verification.
- **Deployment:** [Compose](../../docker-compose.yml) uses machine-specific music
  and playlist mounts and enables debug/docs. A developer homelab setup is not a
  portable, hardened public quickstart.

Historical [PRD-06](06-fastapi-service.md) explicitly deferred auth and emphasized
Jellyfin. Those were earlier scope choices, not evidence of public deployment safety.
This draft proposes revisiting the trust boundary and making Navidrome the first
planned playlist integration. Existing docs are not silently rewritten or superseded.

Assumptions: the intended first audience is technically capable self-hosters with a
lawfully usable music/lyrics library. Public release timing, distribution forms,
maintainer support capacity, and acceptable network exposure are undecided. No
assumption is made that the current lyrics corpus can ship.

## Design

### Public Positioning: Supported Core, Proposed Extension

Supported core: Resonance indexes timestamped lyrics in sections and retrieves songs
by semantic text similarity. It helps a listener explore what songs are about, rather
than relying only on title keywords, genre tags, listening history, or sonic similarity.
Source sections make a result inspectable; relevance remains interpretive.

Proposed extension, explicitly not shipped: combine a seed recording's lyric meaning
with a requested theme, review the ranked list, then save a verified Navidrome playlist.
The example “songs similar to Earth Song by Michael Jackson, talking about broken
promises” illustrates that combined intent, not a claim of currently working end-to-end
playlist generation. Existing M3U output is a separate implemented path.

Public material should distinguish:

- **Available:** lyric parsing/chunking, supported embedding adapters, Qdrant search,
  and the current M3U endpoint, with tested limits and deployment caveats.
- **Proposed:** seed-plus-theme ranking, recording-ID reconciliation, server playlist
  writes, client playback acceptance, and any broader release hardening in this draft.
- **Unproven:** “best,” “only,” superior relevance, universal multilingual quality,
  zero-cloud operation regardless of provider, legal clearance, or production safety.

A local-provider option is real; an unconditional privacy promise is not. Hosted
embedding configurations send content to a provider. Demonstrations should disclose
model, library coverage, rights-cleared examples, and limitations, without publishing
private library paths or presenting a score as a probability of thematic correctness.

### AudioMuse Context, Not a Straw-Man Comparison

[AudioMuse-AI's upstream README](https://github.com/NeptuneHub/AudioMuse-AI), retrieved
2026-10-23, describes sonic analysis, instant playlists, similar-song playlists,
Navidrome/other server integrations, and **Lyrics Search by theme, story, or meaning**.
This is upstream self-description, not independently tested parity or performance.
It is the NeptuneHub open-source project, not the similarly named commercial website.

Therefore, do not claim AudioMuse only analyzes sound, lacks lyric semantics, lacks
Navidrome integration, or proves Resonance is first/unique. Resonance can emphasize
its own section-level lyric retrieval, inspectable evidence, and proposed combined
seed/theme workflow without claiming competitors cannot do the same. These are
product design emphases, not a verified exclusive market advantage.

Before a public comparison, pin the reviewed AudioMuse release/commit, inspect the
relevant implementation/docs, and record a feature/evidence matrix with “not checked”
where appropriate. Any performance or quality comparison needs a shared, rights-cleared
benchmark and reproducible settings. The unverified exclusivity hypothesis in
[PRD-07](07-competitive-landscape.md) must not be repeated as established fact.

### Licensing and Content Release Gate

1. **Project grant and ownership.** Establish who owns contributed code, intended license,
   copyright holders, and distribution forms (source, wheel, container, bundled assets).
   If MIT remains the decision, add the approved tracked LICENSE later and align README,
   package metadata, notices, and distributed artifacts. Do not add a license here or
   treat adding MIT text as resolving third-party obligations.
2. **Mutagen decision — release blocker.** PyPI and installed 1.47.0 metadata declare
   `GPL-2.0-or-later`; the scanner directly imports it. Review the actual license and
   applicable combined-work/distribution obligations. Decide whether the intended
   distribution complies under a compatible licensing approach, requires a dependency
   replacement, or needs qualified licensing advice. Record rationale and required
   notices/source provision. Neither “an MIT project can ignore it” nor “the whole
   repository is automatically GPL in all circumstances” is an acceptable shortcut.
3. **Dependency inventory.** Audit locked direct/transitive dependencies, frontend assets,
   copied code, container images, and build/runtime tools. Record versions, license
   evidence, notices, obligations, and unresolved items for each distributed artifact.
   Source licensing and container redistribution may have different inventories.
4. **Models and weights.** Audit the exact model/revision and distribution method for
   OpenAI service configurations, Ollama examples (including BGE-M3 and Nomic), and
   the Vyakyarth/TEI configuration referenced in Compose. Check model cards, weight
   licenses, conversion/quantization lineage, attribution, usage restrictions, and
   download/redistribution terms. Runtime/adapter licenses do not license weights;
   API service terms are a separate review. No model is approved by mention here.
5. **Lyrics provenance.** Inventory sidecar, embedded, manually supplied, and any crawled
   lyrics sources; record acquisition terms, processing permissions, attribution,
   retention, and redistribution restrictions. Owning audio is not proof of permission
   to redistribute lyrics. Review stored text, excerpts/screenshots, vector exports,
   test fixtures, demo data, logs, and backups individually. Default release proposal:
   code plus original/explicitly licensed synthetic fixtures, no production corpus.
6. **Release manifest.** Record allowed/banned/unresolved assets, source evidence, review
   date, and decision owner. Any unresolved distributed asset is excluded or blocks the
   relevant release. “Audit complete” must refer to an actual inventory, not this PRD.

### Hardening Backlog and Priority/Risk

Priorities below are proposed release gates, not implemented fixes. P0 blocks a broad
public deployment recommendation; merely labeling a service self-hosted is not a control.

- **P0 — Unauthenticated mutations:** select application auth or an enforced/documented
  authenticated perimeter. Authorize playlist writes, ingestion/force replacement,
  and collection listing/deletion as appropriate. Denied requests must produce no
  filesystem/Qdrant side effects; CORS is not authentication.
- **P0 — Request-controlled `data_dir`:** use operator-configured library identifiers
  and allowlisted roots; canonicalize and enforce containment, including symlinks.
  Playlist write locations need narrower permissions than music reads.
- **P0 — Unsafe track paths:** resolve trusted library identity; reject traversal,
  absolute/out-of-library paths, newline/control-character injection, and symlink
  escapes. Validate existence/type; regression-test valid relative-path M3U behavior.
- **P0 — Unsettled rights:** close the licensing gate per shipped artifact; exclude
  uncleared corpus/weights and document obligations before claiming redistribution readiness.
- **P1 — Hardcoded UI origin:** choose same-origin or safe API-base configuration;
  verify remote-browser and HTTPS reverse-proxy use without editing bundled source.
- **P1 — Nonportable Compose/dev defaults:** parameterize/document mounts, separate
  read/write permissions, make debug opt-in, constrain backend access, and smoke-test
  a clean-machine installation.
- **P1 — Error/log disclosure:** review errors, config redaction, request logging,
  embedding requests, and future server credentials; verify with non-secret canaries.

The selected perimeter must cover all exposed API routes and direct Qdrant access, not
just the UI. Bind/publish backend ports only as required. If application auth is deferred,
the shipped deployment must actually enforce the alternative boundary and explain the
risk of bypassing it; advice to “put it behind a proxy” is not proof of protection.

Validate limits for request size, ingestion work, and model-provider cost before exposing
expensive operations. Backup/recovery and destructive-action confirmation need explicit
operator guidance. This draft identifies risks from code review; exploitability/severity
in a particular network remains to be tested, without testing against live private data.

## Acceptance Criteria

Gates for a later readiness effort, not assertions that this documentation task fixes them:

- [ ] An owner approves public scope and support level. Capability claims are checked
      against running code; proposed Navidrome features are clearly labeled proposed.
- [ ] A tracked license grant is approved, and project metadata/README agree with the
      chosen distribution strategy. Mutagen's GPL-2.0-or-later compatibility decision,
      evidence, and compliance actions are recorded; no blocker is hidden by an MIT label.
- [ ] Versioned software/model/weight/content inventories cover actual release artifacts.
      Notices and obligations are satisfied; no uncleared lyrics, private corpus,
      restricted weights, or secrets are shipped, including fixtures and screenshots.
- [ ] Tests show anonymous/unauthorized callers cannot write playlists, scan arbitrary
      roots, replace/delete collections, or bypass the selected boundary via direct
      backend access. Rejected operations have no side effects; authorized use still works.
- [ ] Adversarial path tests cover traversal, absolute paths, alternate separators,
      control characters, symlink escapes, missing files, and arbitrary `data_dir` values.
      Valid supported library paths and existing M3U behavior have regression coverage.
- [ ] Clean-machine Compose onboarding works using documented paths without the author's
      mounts. Remote browser and HTTPS reverse proxy can search without localhost edits;
      backend access and write permissions are constrained as documented.
- [ ] Local/hosted data flows and default logging are tested with canaries. No credentials
      or full private lyrics leak into released files, errors, logs, or public demos.
- [ ] A public comparison cites pinned AudioMuse primary sources and labels untested
      claims. No unsupported exclusivity, superiority, or audio-only competitor claim remains.
- [ ] Existing tests pass; docs links/frontmatter/formatting pass. Future readiness work
      reports actual integration/security checks separately from mocked unit tests.

## Implementation Plan

Tentative review order only; implementation requires a separate decision.

### Phase 1 - Rights and Trust Boundary

- [ ] Decide ownership/license and mutagen strategy; inventory content/model rights.
- [ ] Select supported deployment perimeter and prioritize P0 hardening/test cases.

### Phase 2 - Portable and Verifiable Setup

- [ ] Resolve UI origin and Compose portability; exercise isolated clean-install,
      authorization, path-validation, logging, and regression acceptance checks.

### Phase 3 - Public Presentation

- [ ] Approve supported-versus-proposed capability matrix and sourced competitor context.
- [ ] Review release artifacts and decide whether remaining risks permit publication,
      limited experimental use, or require deferral. Do not claim readiness by default.

## Open Questions

- What license/distribution strategy is intended, who can approve it, and should mutagen
  remain, be replaced, or trigger a different compliance/distribution approach?
- Which exact model revisions and lyrics sources are actually used, and what may be
  processed privately versus redistributed? Who owns the rights review?
- Is the first supported deployment private single-user only, or shared? Will auth live
  in Resonance or a mandatory enforced perimeter, and how are user/owner permissions mapped?
- Which release artifacts, Navidrome/client versions, platforms, and support commitments
  can the maintainer realistically endorse? What evidence permits an experimental label?
- What can be claimed about section evidence and combined seed/theme discovery after
  inspecting a pinned AudioMuse release? No exclusive advantage is assumed in advance.

## References

- [Mutagen 1.47.0 package metadata](https://pypi.org/project/mutagen/1.47.0/)
- [Mutagen upstream COPYING](https://github.com/quodlibet/mutagen/blob/release-1.47.0/COPYING)
- [AudioMuse-AI upstream README](https://github.com/NeptuneHub/AudioMuse-AI)
- [PRD-07 — Competitive landscape (historical hypotheses)](07-competitive-landscape.md)
- [PRD-09 — Navidrome semantic playlists (draft)](09-navidrome-semantic-playlists.md)

External sources reviewed 2026-10-23. AudioMuse was not run or benchmarked; model/content
license audits, perimeter testing, and release clearance remain proposed work.

---

## Changelog

- 2026-10-23: Initial draft — whole-product positioning, rights decisions, and release gates.
