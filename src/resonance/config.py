"""Configuration management — env vars via pydantic-settings, provider configs from YAML."""

import os
import re
from pathlib import Path
from string import Template

import yaml
from dotenv import dotenv_values
from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class QdrantConfig(BaseModel):
    """Qdrant vector database connection."""

    url: str = "http://localhost:6333"
    api_key: SecretStr | None = None


class ChunkingConfig(BaseModel):
    """Chunking parameters for lyric sectioning."""

    gap_threshold_sec: float = 10.0
    min_chunk_lines: int = 2


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
    """One operator-configured Navidrome account, loaded without shell evaluation."""

    model_config = SettingsConfigDict(env_prefix="NAVIDROME_", env_file=".env", extra="ignore")

    base_url: str | None = None
    user_id: str | None = None  # Subsonic login username, not the internal account ID
    user_password: SecretStr | None = None
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
    )

    debug: bool = False  # enables CORS, reload
    serve_docs: bool = False  # enables Swagger UI at /docs
    qdrant: QdrantConfig = QdrantConfig()
    chunking: ChunkingConfig = ChunkingConfig()
    navidrome: NavidromeConfig = Field(default_factory=NavidromeConfig)
    api_token: SecretStr | None = None
    journal_path: Path = Path("data/playlist-operations.sqlite3")


def _expand_env_vars(data: dict) -> dict:
    """Recursively expand ${ENV_VAR} references in string values."""
    result = {}
    for key, value in data.items():
        if isinstance(value, dict):
            result[key] = _expand_env_vars(value)
        elif isinstance(value, str):
            variables = {key: value for key, value in dotenv_values(".env").items() if value is not None}
            result[key] = Template(value).safe_substitute({**variables, **os.environ})
        else:
            result[key] = value
    return result


def _load_yaml(path: Path) -> dict:
    """Load and parse a YAML file with env var expansion."""
    with path.open() as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        return {}
    return _expand_env_vars(data)


def load_provider_config(
    name: str, config_dir: Path | None = None
) -> tuple[str, OpenAIProviderConfig | OllamaProviderConfig]:
    """Load a named provider config from config/{name}.yaml.

    Each config file must have a `type` field ("openai" or "ollama") that
    determines which provider class to use. The filename is the config name.

    Searches: explicit config_dir → config/ → ~/.config/resonance/

    Returns (provider_type, config) tuple.
    Raises ValueError if config file not found or type is unknown.
    """
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", name):
        msg = "Provider configuration name must be a filename stem"
        raise ValueError(msg)
    search_dirs = []
    if config_dir:
        search_dirs.append(config_dir)
    search_dirs.extend(
        [
            Path("config"),
            Path.home() / ".config" / "resonance",
        ]
    )

    for search_dir in search_dirs:
        for ext in ("yaml", "yml"):
            provider_file = search_dir / f"{name}.{ext}"
            if provider_file.is_file():
                data = _load_yaml(provider_file)
                provider_type = data.pop("type", None)
                if provider_type is None:
                    msg = f"config/{name}.yaml missing 'type' field (must be 'openai' or 'ollama')"
                    raise ValueError(msg)
                if provider_type == "openai":
                    return provider_type, OpenAIProviderConfig(**data)
                if provider_type == "ollama":
                    return provider_type, OllamaProviderConfig(**data)
                msg = f"Unknown provider type '{provider_type}' in config/{name}.yaml. Supported: openai, ollama"
                raise ValueError(msg)

    msg = f"Provider config '{name}' not found. Create config/{name}.yaml with a 'type' field."
    raise ValueError(msg)
