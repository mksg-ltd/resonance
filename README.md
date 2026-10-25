# resonance

Search the meaning of lyrics in your Navidrome library. Resonance retrieves track
metadata and synced lyrics through Navidrome APIs, chunks and embeds the lyrics,
and stores searchable sections in Qdrant. No music bind mount is required.

The shared Python application interface serves the CLI and FastAPI. FastAPI endpoints
are the intended contract for both a future Vue application and FastMCP adapter.
Ingestion and library/model setup are administrative tasks. The user-facing goal is
direct lyric search and private playlist creation in Vue, with equivalent MCP tools so
an assistant can do the same using context the user chooses to share. Playback remains
the job of a compatible music client or playback tool.

The current single-account HTML page is an operator PoC for ingestion and search,
not the final user UI. It has no user login or multi-user authorization. The Vue and
MCP experience is an evolving follow-on described in [PRD-12](docs/prds/12-assistant-user-experience.md).

## Setup

Requires Python 3.14+, uv, Docker Compose, a reachable Navidrome account/library, and
an explicitly configured embedding provider. TEI is the local deployment direction;
the existing OpenAI-compatible and Ollama clients remain usable.

```bash
cp .env.example .env
uv sync
```

Edit `.env` with `NAVIDROME_BASE_URL`, `NAVIDROME_USER_ID` (the login username), and
`NAVIDROME_USER_PASSWORD`. Use HTTPS. An explicitly trusted local HTTP deployment
requires `NAVIDROME_ALLOW_HTTP=true`. Keep `NAVIDROME_SERVER_ID` stable; rotate it
and build a new index if rebuilding the server changes song identities.

Set a private `RESONANCE__API_TOKEN` to enable native HTTP operations. Local CLI
execution is the trusted operator interface and does not require that token. Python
and Compose parse `.env`; Make does not source or expand credentials as Make syntax.
Do not commit `.env` or real credentials.

Supported embedding profiles ship in Resonance's bundled catalog. Select a profile
and the endpoint reachable from the process running Resonance in `.env`:

```dotenv
RESONANCE__EMBEDDING__PROFILE=vyakyarth
RESONANCE__EMBEDDING__BASE_URL=http://tei:80/v1
RESONANCE__EMBEDDING__API_KEY=
```

Inside Compose, TEI is reachable at `http://tei:80/v1`; a host-run client uses
`http://localhost:8085/v1`. The catalog contains the profile's model ID, protocol,
and expected dimensions. TEI serves the model selected at service startup, so keep
its `TEI_MODEL_ID` in `.env` aligned with the active profile's `model_id` and restart
TEI when changing models. The profile ID cannot switch a running TEI model.
For Ollama, select `ollama-nomic-text` and set the base URL to the Ollama service
(for example, `http://ollama:11434` in Compose); the profile selects Ollama's API
protocol. For a hosted endpoint, set its base URL and API key explicitly; there is
no cloud fallback. Profile IDs and supported dimensions are listed in
[`embedding_profiles.yaml`](src/resonance/data/embedding_profiles.yaml).

```bash
make up       # Qdrant + TEI dependencies
make run      # dependencies + source API on :8000, Swagger at /docs
# Or: make prod starts the complete Compose stack explicitly.
```

Qdrant uses port 6333; TEI uses 8085. `make down` stops dev dependencies. `make clean`
removes their containers while preserving data and playlist-operation state.

## Inspect a Library

```bash
uv run resonance-library inspect
uv run resonance-library libraries
uv run resonance-library tracks --library 2 --limit 10
uv run resonance-library lyrics --library 2 --song <song-id>
```

Inspection has no indexing or playlist-write side effects. The explicit lyrics
command returns lyric text for the selected song; default logs do not contain it.
Synced lyric offsets are normalized; absent/unsynced-only lyrics are reported.

## Ingest and Search

```bash
uv run resonance-ingest --profile vyakyarth --library 2 --collection home_english_vyakyarth --max-tracks 10
uv run resonance-search --collection home_english_vyakyarth "songs about letting go"
```

Omit `--max-tracks` only when deliberately indexing the full selected library. It
is a run bound, not a claim that the entire library was enumerated. The configured
profile is used by default; `--profile` overrides it for one ingest. Search resolves
the profile ID stored in collection metadata and accepts `--profile` as an optional
compatible override. `--provider` remains a deprecated alias. Exact `--artist`
filtering remains available.

Each native collection binds one server/account/library and one effective embedding
profile, with model/dimensions/chunking/schema metadata. Incompatible scopes/configs
are refused before appending vectors. File-based collections are no longer searchable;
reingest the Navidrome library into a native collection. No collection is
deleted/recreated automatically, and `--data-dir`/`--force` are not native ingestion
inputs.

Song IDs are retained in every section and search hit. Distinct recordings with the
same artist/title remain distinct. Section IDs and lyric/index fingerprints are
stable; incomplete section groups are not searchable. Identical retries can finish
partial writes without duplicates. Changed indexed lyrics require a new collection
until the separate refresh feature implements replacement/cleanup. Missing lyrics
remain eligible for later ingestion. There is no automatic pruning or scheduler.

## Save a Private Playlist

Use an explicit approved selection, repeating `--song` in playback order:

```bash
uv run resonance-playlist create --operation-id my-save-001 --library 2 --name "Letting Go" --song <id-one> --song <id-two>
uv run resonance-playlist status --operation-id my-save-001 --library 2
```

Keep the same operation key and exact input on retries. Keys are unique across the
journal, including account/server/library changes. Duplicate visible names require
`--allow-duplicate-name`. Selections contain 1–100 distinct current library song IDs.
No model call or search regeneration occurs during save.

Private creation is enabled only for the validated Navidrome 0.64.2 release/build
with form POST support. Resonance checks library membership/access before creating,
then verifies the returned exact ID, owner, name, explicit XML privacy, count and
order. Upgrading Navidrome requires validating and updating this gate first.

The SQLite journal records save requests/outcomes, not lyrics or file mappings.
Its default path is `data/playlist-operations.sqlite3`; override with
`RESONANCE__JOURNAL_PATH`. Compose uses a durable `playlist_state` volume at
`/app/state`, writable by appuser. Preserve/back up this journal. Losing it also
loses duplicate-save protection; routine `make clean` preserves it.

`verified` means exact server readback matched. A known-ID `unresolved` operation
can reconcile via status. An unknown-ID `submitting`/`unresolved` outcome must be
inspected manually; retrying the same key never blindly creates again. Do not use
a fresh key to retry an uncertain save. CLI exit codes are 0 for verified, 1 for
failed/invalid requests, and 2 for incomplete/unresolved operations. HTTP returns
the operation state; a 200 response alone does not mean the playlist is verified.
General playlist update/delete and automatic uncertain-outcome repair are deferred.

## HTTP API

| Method     | Path                                                            | Purpose                                             |
| ---------- | --------------------------------------------------------------- | --------------------------------------------------- |
| GET        | `/health`                                                       | Qdrant connectivity                                 |
| GET        | `/api/config`                                                   | Public configuration with secrets excluded/redacted |
| GET/DELETE | `/api/collections[/<name>]`                                     | List bindings / explicitly delete an index          |
| POST       | `/api/search`                                                   | Query a Navidrome-native collection                 |
| POST       | `/api/ingest`                                                   | Protected native library ingestion                  |
| GET        | `/api/navidrome/connection`, `/libraries`, `/tracks`, `/lyrics` | Protected source inspection                         |
| POST       | `/api/navidrome/playlists`                                      | Protected native private save                       |
| GET        | `/api/navidrome/operations/<operation_id>?library_id=2`         | Protected save status/reconciliation                |

All `/api/navidrome/...` paths and native ingestion require `Authorization: Bearer <operator-token>` and a JSON body:

```json
{
  "profile": "vyakyarth",
  "library_id": "2",
  "collection": "home_english_vyakyarth",
  "max_tracks": 10
}
```

Unknown fields, including obsolete mounted-directory inputs, are rejected. The
debug server also serves the page at `/ui`; the local Python-server flow below is
the current PoC workflow. A full frontend is separate work.
`/api/navidrome/playlists` is the supported playlist creation path. The former
local M3U endpoint and raw-LRC inspection command have been removed.

## Development

### Product boundary

- **Admin:** configure Navidrome/embedding services, select libraries, create Qdrant
  collections, ingest, and eventually refresh them.
- **User:** search for tracks related to a theme or conversational context, review
  evidence/candidates, and explicitly create a private Navidrome playlist.
- **Playback:** a Navidrome-compatible client or separate playback integration plays
  the resulting playlist. Resonance does not stream audio.

Navidrome does not act as a general OIDC identity provider. Its external-auth mode
delegates login to a trusted reverse proxy/auth provider; its optional experimental
Jellyfin-compatible API has a client login endpoint but is not an OIDC sign-in flow.
See [PRD-12](docs/prds/12-assistant-user-experience.md) for the current login and
account-mapping questions.

### Local Search and Ingestion PoC

In one terminal, start the local dependencies and debug API:

```bash
make run
```

`make run` binds the development API to loopback at `http://localhost:8000`. In a
second terminal, serve the static page from the `ui/` directory on a different port:

```bash
cd ui
python -m http.server 8080 --bind 127.0.0.1
```

Open `http://localhost:8080`, enter `RESONANCE__API_TOKEN` from your local `.env`,
and load the available Navidrome libraries. The token stays in the page's memory and
is sent only to protected library-listing and ingestion requests. The debug API allows
the two local page origins on port 8080 for CORS; its dev server listens only on
loopback. Do not expose this PoC setup to a network.

The ingestion form defaults to 10 tracks. Clear the limit only when you intend to
process the whole selected library; the request is synchronous and has no progress
updates. If the browser loses its response, the run may have completed. Retrying the
same compatible collection skips unchanged tracks and resumes identical partial writes.
This operation adds newly visible songs but does not replace changed lyrics or remove
deleted songs. The UI does not reset or delete collections.

```bash
make test
make lint
uv run ty check src/
make build
```

Tests use synthetic lyrics, real local Qdrant/SQLite for persistence contracts, and
mocked external APIs. Live probes are bounded and must not run a whole-library
embedding migration implicitly. See [PRD-09](docs/prds/09-navidrome-semantic-playlists.md)
and the [live validation record](docs/plans/2026-10-25-navidrome-validation.md).

Native save accepts `operation_id`, `library_id`, `name`, ordered `song_ids`, and
optional `allow_duplicate_name`. These map directly to the CLI selection above.
The inspection subpaths shown in the table share the `/api/navidrome` prefix.
