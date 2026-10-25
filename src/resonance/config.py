"""Runtime settings from environment variables and .env."""

import os
from pathlib import Path

from pydantic import AliasChoices, BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class QdrantConfig(BaseModel):
    """Qdrant vector database connection."""

    url: str = "http://localhost:6333"
    api_key: SecretStr | None = None


class ChunkingConfig(BaseModel):
    """Chunking parameters for lyric sectioning."""

    gap_threshold_sec: float = 10.0
    min_chunk_lines: int = 2


class EmbeddingRuntimeConfig(BaseModel):
    """Runtime endpoint selection for a bundled embedding profile."""

    profile: str = "vyakyarth"
    base_url: str | None = None
    api_key: SecretStr | None = None


class OpenAIProviderConfig(BaseModel):
    """OpenAI-compatible embedding configuration.

    Works with OpenAI API, or any OpenAI-compatible server (e.g., HuggingFace TEI).
    Set base_url to point at a local server.
    """

    api_key: SecretStr = SecretStr("dummy")  # not needed for local servers like TEI
    model: str = "text-embedding-3-small"
    base_url: str | None = None  # e.g., "http://localhost:8080/v1" for TEI
    dimensions: int | None = Field(default=None, gt=0)  # expected server output dimensions
    revision: str | None = None

    @property
    def effective_base_url(self) -> str:
        """Resolve SDK environment behavior once for transport, profile and cache."""
        return (self.base_url or os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")


class OllamaProviderConfig(BaseModel):
    """Ollama-specific embedding configuration."""

    base_url: str = "http://localhost:11434"
    model: str = "nomic-embed-text"
    dimensions: int | None = Field(default=None, gt=0)
    revision: str | None = None


class NavidromeConfig(BaseSettings):
    """Navidrome server connection settings, loaded without shell evaluation."""

    model_config = SettingsConfigDict(env_prefix="NAVIDROME_", env_file=".env", extra="ignore")

    base_url: str | None = None
    server_id: str = "home"
    allow_http: bool = False
    timeout: float = Field(default=20, gt=0, le=300)
    page_size: int = Field(default=500, ge=1, le=500)
    max_pages: int = Field(default=200, ge=1)
    lyrics_language: str | None = None


class Settings(BaseSettings):
    """Application settings — all from env vars.

    Env var prefix: RESONANCE__
    Examples:
        RESONANCE__DEBUG=true
        RESONANCE__SERVE_DOCS=true
        RESONANCE__QDRANT__URL=http://qdrant:6333
        RESONANCE__CHUNKING__GAP_THRESHOLD_SEC=8.0
    """

    model_config = SettingsConfigDict(
        env_prefix="RESONANCE__",
        env_nested_delimiter="__",
        env_file=".env",
        extra="ignore",
        populate_by_name=True,
    )

    debug: bool = False  # enables local HTTP and reload
    serve_docs: bool = False  # enables Swagger UI at /docs
    trusted_proxy_ips: str = "127.0.0.1"
    qdrant: QdrantConfig = QdrantConfig()
    chunking: ChunkingConfig = ChunkingConfig()
    embedding: EmbeddingRuntimeConfig = Field(default_factory=EmbeddingRuntimeConfig)
    navidrome: NavidromeConfig = Field(default_factory=NavidromeConfig)
    admin_user: str | None = Field(
        default=None,
        validation_alias=AliasChoices("RESONANCE_ADMIN_USER", "RESONANCE__ADMIN_USER"),
    )
    journal_path: Path = Path("data/playlist-operations.sqlite3")
