# Resonance v1 Roadmap

This is the lightweight tracker for the three product pillars currently gating a v1
decision. A completed implementation is not the same as end-to-end acceptance or
release readiness.

## V1 Gates

### 1. Admin collection setup

- [x] Admin Vue workflow to choose a Navidrome library and embedding profile, create a
      collection through ingestion, and make it available to search.
- [x] Live aggregate progress and cooperative stop/resume implementation; operator
      acceptance is still pending. See [PRD-15](prds/15-admin-ingestion-jobs.md).
- [ ] Operator acceptance: create a bounded collection from the Vue UI, confirm it
      appears in the search collection list, and run a search against it.
- [ ] Operator acceptance: observe a bounded ingestion run, stop at a safe point, resume
      it, and confirm the resulting collection is searchable. Incremental refresh for
      changed/deleted tracks remains deferred.
- Implementation: [admin collection setup plan](plans/2026-10-26-admin-collection-creation.md)
  (merged to `main` in `cc34d69`).

### 2. Actual MCP tools

- [ ] Discuss and specify the first user-facing tool contracts, authentication lifecycle,
      library-scoped search, grounded results, and explicit playlist-save intent.
- [ ] Write and approve the implementation PRD before building the tools.
- [x] Foundation scaffold exists: authenticated, tool-free FastMCP at `/mcp/`.
- Spec: [PRD-14 FastMCP scaffold](prds/14-fastmcp-scaffold.md).

### 3. Open-source readiness

- [x] Reconcile and scope [PRD-10](prds/10-public-positioning-open-source-readiness.md)
      against the current Navidrome product and release-readiness needs.
- [x] Select AGPL-3.0-only as the project license.
- [x] Add the AGPL-3.0-only license text and align Python package metadata.
- [ ] Complete the distribution inventory, notices, and release artifact review.
- [ ] Resolve the remaining release gates for dependency/content rights, trust
      boundary, portable deployment, secret/log handling, and accurate capability claims.
- [ ] Publish the self-hosting guide, contributor guide, and project history index;
      verify they match a clean install and current service paths.
- Do not label the project distribution-ready until the agreed gates have evidence.

## Playlist Visibility Follow-up

- [x] Source-check the Resonance create/readback path: the Subsonic `createPlaylist`
      call sends name and ordered song IDs; it does not send a visibility field. The save
      is marked verified only when readback matches the caller as owner, `public=false`,
      name, count, and order. See `src/resonance/navidrome.py` and
      `src/resonance/application/playlists.py`.
- [x] Check Navidrome 0.64.2 behavior: API-created playlists default to private. The
      API returns explicit `public=false` in XML; false may be omitted from JSON. The
      Subsonic `createPlaylist` method has no visibility argument; visibility can be changed
      later through `updatePlaylist`. See the version-pinned [playlist creation
      implementation](https://github.com/navidrome/navidrome/blob/v0.64.2/core/playlists/playlists.go#L1108)
      and [Subsonic response type](https://github.com/navidrome/navidrome/blob/v0.64.2/server/subsonic/responses/responses.go#L2087).
- [ ] Confirm whether `mk` is a Navidrome administrator. Navidrome's maintainer states
      that administrators can see and modify any playlist, including another user's
      private playlist; this would explain the observation without a public flag.
      Reference: [Navidrome multi-user playlist visibility](https://github.com/navidrome/navidrome/discussions/2306).
- [ ] If `mk` is not an administrator, verify the affected playlist by exact ID as its
      owner: record owner and explicit XML `public` value, then test visibility with a
      regular non-admin account. If it is public, treat this as a creation/readback bug and
      fix it before v1. Do not put credentials or full song/lyric data in this tracker.
- Live two-account behavior has not been reproduced in this environment; the source
  check is not a claim that the user's observed playlist is confirmed private.

## Other Acceptance

- [ ] Operator evaluates search-match quality and the authenticated search → review →
      private-playlist flow against the real library.
- [ ] Complete the Navidrome visibility follow-up above before declaring private-playlist
      ownership behavior accepted for v1.
