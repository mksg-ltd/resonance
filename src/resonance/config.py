"""Configuration management — YAML + env var loading via pydantic-settings."""

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, SecretStr
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict


class EmbeddingConfig(BaseModel):
    """Which embedding provider to use."""

    provider: str = "openai"


class QdrantConfig(BaseModel):
    """Qdrant vector database connection."""

    url: str = "http://localhost:6333"
    collection: str = "lyrics"
    api_key: SecretStr | None = None


class ChunkingConfig(BaseModel):
    """Chunking parameters for lyric sectioning."""

    gap_threshold_sec: float = 10.0
    min_chunk_lines: int = 2


class PlaylistConfig(BaseModel):
    """Playlist generation settings."""

    dir: str | None = None


class JellyfinConfig(BaseModel):
    """Jellyfin integration (future)."""

    url: str | None = None
    api_key: SecretStr | None = None


class ServerConfig(BaseModel):
    """FastAPI server settings."""

    host: str = "0.0.0.0"  # noqa: S104
    port: int = 8000
    debug: bool = False


class OpenAIProviderConfig(BaseModel):
    """OpenAI-specific embedding configuration."""

    api_key: SecretStr
    model: str = "text-embedding-3-small"


class OllamaProviderConfig(BaseModel):
    """Ollama-specific embedding configuration."""

    base_url: str = "http://localhost:11434"
    model: str = "nomic-embed-text"


# Module-level storage for YAML data to feed into settings sources.
_yaml_data: dict = {}


class YamlSettingsSource(PydanticBaseSettingsSource):
    """Custom settings source that reads from pre-loaded YAML data."""

    def get_field_value(self, field, field_name):
        return _yaml_data.get(field_name), field_name, False

    def __call__(self):
        return {k: v for k, v in _yaml_data.items() if k in self.settings_cls.model_fields}


class Settings(BaseSettings):
    """Application settings loaded from YAML + env vars."""

    model_config = SettingsConfigDict(
        env_prefix="RESONANCE__",
        env_nested_delimiter="__",
    )

    embedding: EmbeddingConfig = EmbeddingConfig()
    qdrant: QdrantConfig = QdrantConfig()
    chunking: ChunkingConfig = ChunkingConfig()
    jellyfin: JellyfinConfig = JellyfinConfig()
    playlists: PlaylistConfig = PlaylistConfig()
    server: ServerConfig = ServerConfig()

    @classmethod
    def settings_customise_sources(
        cls, settings_cls, init_settings, env_settings, dotenv_settings, file_secret_settings
    ):
        """Priority: init → env vars → YAML → defaults."""
        return (init_settings, env_settings, YamlSettingsSource(settings_cls), file_secret_settings)


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


def _find_config_file() -> Path | None:
    """Find config file: env var → local → user home.

    Checks both .yaml and .yml extensions.
    """
    env_path = os.environ.get("RESONANCE_CONFIG")
    if env_path:
        path = Path(env_path)
        if path.is_file():
            return path

    # Local directory — check both flat and config/ subdirectory layouts
    for candidate in [
        Path("config.yaml"),
        Path("config.yml"),
        Path("config/config.yaml"),
        Path("config/config.yml"),
    ]:
        if candidate.is_file():
            return candidate

    home = Path.home() / ".config" / "resonance" / "config.yaml"
    if home.is_file():
        return home

    return None


def _load_yaml(path: Path) -> dict:
    """Load and parse a YAML file with env var expansion."""
    with path.open() as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        return {}
    return _expand_env_vars(data)


def load_provider_config(
    provider: str, config_dir: Path | None = None
) -> OpenAIProviderConfig | OllamaProviderConfig | None:
    """Load provider-specific config from conf.d/{provider}.yaml.

    Searches: explicit config_dir → conf.d/ → config/conf.d/ → ~/.config/resonance/conf.d/
    """
    search_dirs = []
    if config_dir:
        search_dirs.append(config_dir)
    search_dirs.extend(
        [
            Path("conf.d"),
            Path("config/conf.d"),
            Path.home() / ".config" / "resonance" / "conf.d",
        ]
    )

    for search_dir in search_dirs:
        for ext in ("yaml", "yml"):
            provider_file = search_dir / f"{provider}.{ext}"
            if provider_file.is_file():
                data = _load_yaml(provider_file)
                if provider == "openai":
                    return OpenAIProviderConfig(**data)
                if provider == "ollama":
                    return OllamaProviderConfig(**data)
                return None

    return None


def load_settings(config_path: Path | None = None) -> Settings:
    """Load settings from YAML file + env vars.

    Priority: code defaults → YAML file → env vars.
    YAML is loaded into a custom settings source so env vars take precedence.
    """
    global _yaml_data  # noqa: PLW0603
    path = config_path or _find_config_file()
    _yaml_data = _load_yaml(path) if path and path.is_file() else {}
    try:
        return Settings()
    finally:
        _yaml_data = {}
