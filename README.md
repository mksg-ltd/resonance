# resonance

Semantic search for your music library. Describe a mood, theme, or feeling — get matching songs back, ranked by lyric similarity.

Built for self-hosters running Jellyfin. Works entirely on your own hardware with local models, or use OpenAI for higher quality embeddings.

## How it works

```
Your music library (LRC files)
  → Parse timestamped lyrics
  → Chunk into song sections (verse, chorus, bridge)
  → Generate vector embeddings (OpenAI or Ollama)
  → Store in Qdrant vector database
  → Search by meaning, not keywords
```

Ask for "songs about letting go and moving on" and get results ranked by semantic similarity — not keyword matching.

## Quick start

### Prerequisites

- Docker and Docker Compose
- An OpenAI API key (or a running Ollama instance for local embeddings)
- LRC lyrics files for your music library

### 1. Clone and configure

```bash
git clone https://github.com/youruser/resonance.git
cd resonance

# Copy example configs
cp config/config.yaml.example config/config.yml
cp config/conf.d/openai.yaml.example config/conf.d/openai.yaml

# Edit config/conf.d/openai.yaml and set your API key
```

### 2. Start the services

```bash
docker compose up -d
```

This starts:

- **Qdrant** — vector database on port 6333
- **resonance** — API service on port 8000

### 3. Ingest your lyrics

```bash
curl -X POST http://localhost:8000/api/ingest -H "Content-Type: application/json" -d '{}'
```

### 4. Search

```bash
curl -X POST http://localhost:8000/api/search \
  -H "Content-Type: application/json" \
  -d '{"query": "songs about heartbreak and rain"}'
```

### 5. Swagger UI

Enable debug mode in `config/config.yml`:

```yaml
server:
  debug: true
```

Then visit `http://localhost:8000/docs` for the interactive API explorer.

## Configuration

### Main config (`config/config.yml`)

```yaml
embedding:
  provider: openai # openai | ollama

qdrant:
  url: http://localhost:6333
  collection: lyrics

chunking:
  gap_threshold_sec: 10.0
  min_chunk_lines: 2

server:
  host: 0.0.0.0
  port: 8000
  debug: false
```

### Provider configs (`config/conf.d/`)

Each provider gets its own file. Only the active provider's file is loaded.

**OpenAI** (`config/conf.d/openai.yaml`):

```yaml
api_key: ${OPENAI_API_KEY} # reads from environment variable
model: text-embedding-3-small # or text-embedding-3-large for higher quality
```

**Ollama** (`config/conf.d/ollama.yaml`):

```yaml
base_url: http://localhost:11434
model: nomic-embed-text # or mxbai-embed-large
```

### Environment variable overrides

Any config value can be overridden with environment variables:

```bash
RESONANCE__QDRANT__URL=http://qdrant:6333
RESONANCE__SERVER__DEBUG=true
RESONANCE__EMBEDDING__PROVIDER=ollama
```

## Fully self-hosted setup

No cloud dependencies required. Use Ollama for local embeddings:

```yaml
# config/config.yml
embedding:
  provider: ollama
```

```yaml
# config/conf.d/ollama.yaml
base_url: http://ollama:11434
model: nomic-embed-text
```

Add Ollama to your `docker-compose.yml`:

```yaml
services:
  ollama:
    image: ollama/ollama:latest
    volumes:
      - ollama_data:/root/.ollama
    # Pull the model: docker exec ollama ollama pull nomic-embed-text
```

Stack: Jellyfin + Qdrant + Ollama + resonance. Zero cloud dependencies.

## API endpoints

| Method   | Path                      | Description                           |
| -------- | ------------------------- | ------------------------------------- |
| `POST`   | `/api/search`             | Semantic lyric search                 |
| `POST`   | `/api/ingest`             | Trigger lyrics ingestion              |
| `GET`    | `/api/config`             | Current config (secrets redacted)     |
| `GET`    | `/api/collections`        | List Qdrant collections with metadata |
| `DELETE` | `/api/collections/{name}` | Drop a collection                     |
| `GET`    | `/health`                 | Service health check                  |

## Docker Compose

The default `docker-compose.yml` runs resonance alongside Qdrant. Mount your music library and config:

```yaml
services:
  resonance:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./config:/app/config:ro
      - /path/to/your/music:/data/media/music/english:ro
    environment:
      - RESONANCE__QDRANT__URL=http://qdrant:6333
    depends_on:
      - qdrant
```

## CLI tools

For local development or scripting:

```bash
# Search
uv run resonance-search "songs about hope" --artist "Coldplay" --limit 10

# Ingest
uv run resonance-ingest --gap 8.0 --data-dir ./my-lyrics/
```

## Development

```bash
make install    # Install deps + pre-commit hooks
make run        # Start dev server with auto-reload
make test       # Run tests
make lint       # Check code style
make build      # Build Docker image
```

## License

MIT
