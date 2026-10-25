# Navidrome Protocol Validation — 2026-10-25

Status: Protocol and production CLI private-save verification complete; API/CLI ingestion/search/save tested with isolated local persistence.

Related: [PRD-09](../prds/09-navidrome-semantic-playlists.md) and
[the accepted architecture decision](../adr/001-navidrome-application-boundary.md).

## Environment and Scope

- Server: Navidrome **0.64.2 (10114574)**.
- Subsonic API: **1.16.1**, OpenSubsonic enabled.
- Relevant advertised extensions: `formPost` version 1 and `songLyrics` versions 1/2.
- One account, with the test scoped to **English**, `musicFolderId=2`.
  Other visible folders were not included in the library inventory or playlist selection.
- Credentials and base address were read from the local, ignored `.env`; passwords,
  authentication tokens, full lyric text, and filesystem paths were not printed.
  No embedding/LLM calls, index writes, audio downloads, or changes to existing user
  playlists were performed.

## Read-Only Library and Lyric Checks

- `ping` authenticated successfully using token/salt parameters in form POST bodies.
- `getMusicFolders` identified available libraries.
- Paged `search3` with an empty query and explicit folder 2 returned **4,187 tracks**,
  each with a unique song ID. There were ten page requests, including the final empty
  page; no missing/repeated IDs were encountered.
- `getLyricsBySongId` returned synced lyrics for all ten tracks sampled across that
  complete listing. An earlier first-page sample also returned synced lyrics.
  This validates API availability and sampled coverage, not full lyric coverage.
- Structured results include timestamped lines suitable for translation into the
  chunker's domain input. The samples use language `xxx` in the initial probe;
  language-selection policy must handle unknown-language values explicitly.

Implication: the first-party API can supply song identity, metadata, and sampled synced
lyrics. The new ingestion design does not require Resonance to read mounted audio/LRC
files or maintain a filename-to-song-ID mapping. Production ingestion now uses the normalized adapter; isolated Qdrant tests and runtime verify the migration. No live library reindex was performed.

## Private Creation and Exact Readback

The original protocol probe created one test playlist:

- Name: **Resonance API test 2026-10-25 010011 UTC**.
- ID: `54KTiHBivSv80nWnJ3x1nK`.

Sequence:

1. Selected three distinct songs through folder-scoped listing and validated their
   exact IDs using `getSong`.
2. Created the named playlist empty through `createPlaylist`, without any visibility
   follow-up. Retained the returned exact ID in a local probe journal.
3. Read back that ID as XML: `public="false"`, expected owner/name, and zero songs.
4. Populated that same owned test playlist using `createPlaylist` with its exact
   `playlistId` and repeated ordered `songId` values. No other playlist was targeted.
5. Read back the exact ID again and verified owner, name, private visibility, count 3,
   and the complete ordered song-ID sequence.

The final order is:

| Position | Artist | Title                |
| -------- | ------ | -------------------- |
| 1        | Akon   | Akon’s Beautiful Day |
| 2        | Adele  | To Be Loved          |
| 3        | Adele  | Hold On              |

The user confirmed that the API-created playlist and all three entries were visible,
and later confirmed audible playback/advancing in a browser. Exact browser/client
version and the private setting as displayed in that UI were not supplied. The playlist
is retained for inspection.

### Visibility Serialization Finding

The first conservative JSON check could not establish privacy because the `public`
field was absent. No tracks were added while that result was unresolved.

For this version, the response definition serializes a false `public` value with
JSON omission, while XML includes the explicit boolean attribute. This was confirmed
against the [version-pinned response source](https://github.com/navidrome/navidrome/blob/v0.64.2/server/subsonic/responses/responses.go#L280)
and live XML readback. The [version-pinned create implementation](https://github.com/navidrome/navidrome/blob/v0.64.2/core/playlists/playlists.go#L108)
also constructs a new playlist with the default false visibility.

The probe then verified the existing empty playlist as private before populating it;
it did not issue another create or use `updatePlaylist(public=false)` to change privacy.
Do not treat a missing visibility field on an arbitrary unvalidated server as proof
of privacy. Prefer explicit XML verification or a deliberately versioned interpretation.

## Production Operations and Runtime Verification

The installed production `resonance-library inspect` command reproduced Navidrome
0.64.2 (10114574), protocol 1.16.1 and the expected extensions.

A separate bounded production `resonance-playlist create` accepted the original three
approved song IDs in the same order. It made one direct create with all three IDs,
then verified exact ID, owner, name, XML `public=false`, count and order:

- Name: **Resonance production CLI test 20261025T025707Z**.
- ID: `6egbBrXJuCndCtmRrAuzHu`.
- Operation: `acceptance-20261025T025707Z`.
- Result: `verified`; repeating the exact command returned the same persisted ID.
- The journal is the normal ignored `data/playlist-operations.sqlite3`. Its operation
  and an ignored summary retain the result. No embedding calls were made.
- This production-created playlist is retained for inspection. Browser playback was
  confirmed for the earlier protocol playlist, not asserted for this new playlist.

An isolated uvicorn HTTP runtime used the actual checkout modules, on-disk Qdrant and
SQLite, plus mocked Navidrome/embedding HTTP transports. Three synthetic songs were
ingested, returned by search, saved in exact order and retried without a duplicate.
Invalid input, stale IDs, private-readback mismatch, ambiguous timeout and unauthorized
requests produced the expected failures/states. This did not access the live library.

## Acceptance Record and Limits

- [ ] Record the playback client name and version.
- [x] Operator confirmed audible playback/advancing through the test in a browser.
- [ ] Confirm the private setting as displayed in the intended client/account.
- [x] Reusable application/CLI/HTTP operations exercised with real local persistence and production CLI live acceptance.
- [x] Caller authorization, concurrent journal claims, timeout/restart reconciliation and stale-song behavior tested.
- [x] API ingestion/search validated in isolated new collections; music mount removed.
- [ ] Operator-run live library indexing remains a deliberate follow-up; no bulk reindex was performed.

Probe summaries and the test operation record are under ignored `data/`; no secrets
or full lyrics are stored in these summaries. The production journal's storage choice
remains independent of this one-off probe.

## Operator Follow-up

The user subsequently reported that ingestion and semantic search both work in their
local setup. The exact launch mode, collection name, number of tracks, and embedding
profile were not supplied; no counts or specific command output are inferred from this
confirmation. A small run is available through `--max-tracks`; this bounds discovered
tracks, while the processed/indexed count can be lower when lyrics are missing or
unsynced.
