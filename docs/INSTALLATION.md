# Installation and operation

This guide is for a self-hosted Resonance instance connected to one Navidrome server.
Resonance reads library metadata and synced lyrics from Navidrome, writes vectors and
lyric sections to local Qdrant, and stores playlist-save operation records in SQLite.
It does not need access to the music files themselves.

## Requirements

- Docker Engine with the Compose plugin.
- A reachable Navidrome server and an account with an accessible music library.
- A host able to run the selected embedding service and model. The included Compose
  service runs Hugging Face Text Embeddings Inference (TEI) on CPU; available memory
  and performance depend on the model and library size.
- A supported embedding profile. Check the [bundled catalog](../src/resonance/data/embedding_profiles.yaml)
  and the model's own license and usage terms.

The repository's Compose file currently binds Resonance, Qdrant, and TEI ports to
loopback for local development. The Resonance Compose service also enables debug mode
for local sign-in. Treat this setup as local-only; do not expose it directly to a LAN
or the internet. The release hardening and platform verification are still open in the
[v1 roadmap](roadmap.md).

## Configure and start

From the repository root:

```bash
cp .env.example .env
```

Set `NAVIDROME_BASE_URL` and `RESONANCE_ADMIN_USER` in `.env`. The admin value is the
Navidrome username allowed to perform administrative ingestion and collection
operations. Do not put a Navidrome password in `.env`: users sign in through the UI
with their own account. Protect `.env` and never commit it.

The default profile is configured for the bundled TEI service. Ensure `TEI_MODEL_ID`
in `.env` matches the model ID in the selected profile. For a hosted OpenAI-compatible
endpoint, configure its base URL and API key using `RESONANCE__EMBEDDING__BASE_URL` and
`RESONANCE__EMBEDDING__API_KEY`. For Ollama, choose an Ollama profile and set its
reachable service URL. The embedding endpoint receives lyric text during ingestion
and query text during search; review the provider's data handling before selecting a
hosted service. Local inference avoids sending those texts to a hosted embedding
provider, but model downloads and other configured services still have their own
network behavior.

Start the Compose stack:

```bash
make prod
```

The UI is at <http://127.0.0.1:8000/>. Sign in with a Navidrome account. An admin
account can select a library and profile and create a collection by starting
ingestion. Begin with the default 10-track sample, check progress and search quality,
then clear the limit only when ready to ingest the whole library. Ingestion can be
stopped at safe work boundaries and explicitly resumed from the UI.

## Embedding and indexing experiments

The code is intended to be inspectable. Start with the README's
[learning path](../README.md#learning-path-from-lyrics-to-semantic-search), then trace
these files:

- `src/resonance/chunker.py` — tag-first and timestamp-gap lyric chunking.
- `src/resonance/data/embedding_profiles.yaml` — model IDs, protocols, and dimensions.
- `src/resonance/embedders/` — embedding request clients.
- `src/resonance/application/indexing.py` — collection metadata, fingerprints, and
  Qdrant writes.
- `src/resonance/application/search.py` — query embedding, vector retrieval, and
  candidate construction.

Use a separate collection for experiments with another model or chunking policy.
Vectors from different models or model revisions generally do not share a comparable
space, and a collection's dimensions and index metadata are checked before writes.
Resonance currently resumes identical partial writes; it does not reconcile changed
lyrics or remove tracks deleted from Navidrome. A new collection is the safe way to
compare a materially different indexing setup.

## Data and backups

All service artifacts are under the ignored root `data/` directory:

| Path                   | Contents                                                  |
| ---------------------- | --------------------------------------------------------- |
| `data/qdrant_storage/` | Qdrant collections, vectors, lyric sections, and metadata |
| `data/tei_cache/`      | Local TEI model cache                                     |
| `data/resonance/`      | Compose playlist-save journal                             |
| `data/local/`          | Host-run playlist-save journal                            |

Back up `data/` while the services are stopped or use a database-aware backup process.
The SQLite journal contains operation names, track IDs, and save outcomes, not lyrics.
It prevents a retry from blindly duplicating a playlist when a previous Navidrome
create request had an uncertain result. Preserve it alongside Qdrant data.

The first Compose startup after migration from the old `playlist_state` named volume
copies the old journal into `data/resonance/`. Keep the named volume until the copy has
been confirmed. `make prod` recreates containers and interrupts an active ingestion;
wait for it to finish before updates or restarts. In-memory job progress and login
sessions do not survive a restart, but completed Qdrant writes remain and identical
ingestion work can resume.

To stop the stack while keeping data, use `make prod-down`. To remove a collection,
use the admin UI/API. To remove all instance data, first stop the stack, then remove
the contents of `data/` and the legacy `playlist_state` volume if it is no longer
needed. This permanently deletes indexed lyrics, vectors, caches, and the operation
journal.

## Remote access and security

The included Compose configuration is intended for local-only use. For remote access,
use a TLS-terminating reverse proxy with an exact configured trusted proxy address.
The proxy must preserve the accepted public `Host` and reject unknown hosts; do not
enable forwarded HTTPS headers for untrusted peers. Do not expose Qdrant or TEI ports
to untrusted networks. See [AGENTS.md](../AGENTS.md) for the repository's current
network and data-boundary notes; PRD-10 tracks the remaining hardening work.

## Developer setup

For source development, install Python dependencies and frontend packages, then run
the API and Vite separately:

```bash
uv sync
pnpm --dir vue-ui install
make run
make ui
```

The API is at <http://127.0.0.1:8000/> and Vite at <http://127.0.0.1:5173/>. Vite
proxies `/api` calls to FastAPI. See the root README for CLI inspection, bounded
ingestion, and search examples.
