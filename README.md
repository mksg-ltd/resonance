# resonance

Search the meaning of lyrics in your Navidrome library. Resonance retrieves track
metadata and synced lyrics through Navidrome APIs, chunks and embeds the lyrics,
and stores searchable sections in Qdrant. No music bind mount is required.

The shared Python application interface serves the CLI and FastAPI. The current
backend work adds library-native ingestion/search and verified private playlist
creation; automatic seed/theme generation, a Vue frontend, MCP, and scheduled
library refresh are separate follow-ons.

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

Embedding profiles are named YAML files under `config/` or `~/.config/resonance/`.
An OpenAI-compatible TEI profile looks like:

```yaml
type: openai
base_url: http://localhost:8085/v1
api_key: dummy
model: krutrim-ai-labs/Vyakyarth
dimensions: 768
```

Use the endpoint reachable from the process running Resonance. Within Compose,
TEI is reachable as `http://tei/v1`; host-run clients use the published port 8085.
Use the actual served model and dimensions. Configure a revision when known and
create a new collection after changing model weights. Provider type describes the
API transport; it is not proof of the model's identity. Explicitly configuring a
hosted endpoint sends selected lyric sections/search text there; no cloud fallback
is performed.

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
uv run resonance-ingest --provider vyakyarth --library 2 --collection home_english_vyakyarth --max-tracks 10
uv run resonance-search --collection home_english_vyakyarth "songs about letting go"
```

Omit `--max-tracks` only when deliberately indexing the full selected library. It
is a run bound, not a claim that the entire library was enumerated. Provider config
can be selected automatically from collection metadata during search; `--provider`
is an optional compatible override. Exact `--artist` filtering remains available.

Each native collection binds one server/account/library and one effective embedding
profile, with model/dimensions/chunking/schema metadata. Incompatible scopes/configs
are refused before appending vectors. Existing file-based collections stay readable;
choose a new native collection for the migration. No collection is deleted/recreated
automatically, and `--data-dir`/`--force` are not native ingestion inputs.

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
| POST       | `/api/search`                                                   | Query a selected native or legacy collection        |
| POST       | `/api/ingest`                                                   | Protected native library ingestion                  |
| GET        | `/api/navidrome/connection`, `/libraries`, `/tracks`, `/lyrics` | Protected source inspection                         |
| POST       | `/api/navidrome/playlists`                                      | Protected native private save                       |
| GET        | `/api/navidrome/operations/<operation_id>?library_id=2`         | Protected save status/reconciliation                |
| POST       | `/api/playlists`                                                | Legacy explicit-path M3U file creation              |

All `/api/navidrome/...` paths and native ingestion require `Authorization: Bearer <operator-token>` and a JSON body:

```json
{
  "provider": "vyakyarth",
  "library_id": "2",
  "collection": "home_english_vyakyarth",
  "max_tracks": 10
}
```

Unknown fields, including obsolete mounted-directory inputs, are rejected. The
static debug search page remains at `/ui`; the full frontend is separate work.
Legacy M3U creation still operates on explicitly submitted paths/output directories;
it is not part of native Navidrome playback or a reason to restore a music mount.
Raw LRC inspection remains available through `resonance-chunks file.lrc`.

## Development

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
