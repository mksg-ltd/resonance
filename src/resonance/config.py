"""Configuration management — env vars via pydantic-settings, provider configs from YAML."""

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, SecretStr
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
    dimensions: int | None = None  # override auto-detected dimensions


class OllamaProviderConfig(BaseModel):
    """Ollama-specific embedding configuration."""

    base_url: str = "http://localhost:11434"
    model: str = "nomic-embed-text"


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
    )

    debug: bool = False  # enables CORS, reload
    serve_docs: bool = False  # enables Swagger UI at /docs
    qdrant: QdrantConfig = QdrantConfig()
    chunking: ChunkingConfig = ChunkingConfig()


def _expand_env_vars(data: dict) -> dict:
    """Recursively expand ${ENV_VAR} references in string values."""
    result = {}
    for key, value in data.items():
        if isinstance(value, dict):
            result[key] = _expand_env_vars(value)
        elif isinstance(value, str):
            result[key] = os.path.expandvars(value)
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
