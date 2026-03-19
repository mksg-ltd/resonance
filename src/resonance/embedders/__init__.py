"""Embedding provider abstraction — factory and re-exports."""

from pathlib import Path

from resonance.config import Settings, load_provider_config

from .base import EmbeddingProvider
from .ollama import OllamaEmbedder
from .openai import OpenAIEmbedder

__all__ = ["EmbeddingProvider", "OllamaEmbedder", "OpenAIEmbedder", "create_embedder", "get_embedder_for_provider"]


def create_embedder(settings: Settings, config_dir: Path | None = None) -> EmbeddingProvider:
    """Create the appropriate embedder based on config.

    Reads embedding.provider from settings, loads provider-specific config
    from conf.d/{provider}.yaml, and returns the right embedder instance.
    """
    provider = settings.embedding.provider
    provider_config = load_provider_config(provider, config_dir=config_dir)

    if provider == "openai":
        if provider_config is None:
            msg = (
                "OpenAI provider selected but no conf.d/openai.yaml found. "
                "Copy conf.d/openai.yaml.example to conf.d/openai.yaml and set your API key."
            )
            raise ValueError(msg)
        return OpenAIEmbedder(provider_config)

    if provider == "ollama":
        if provider_config is None:
            msg = (
                "Ollama provider selected but no conf.d/ollama.yaml found. "
                "Copy conf.d/ollama.yaml.example to conf.d/ollama.yaml."
            )
            raise ValueError(msg)
        return OllamaEmbedder(provider_config)

    msg = f"Unknown embedding provider: {provider}. Supported: openai, ollama"
    raise ValueError(msg)


# Cache of embedders by "provider:model" key
_embedder_cache: dict[str, EmbeddingProvider] = {}


def get_embedder_for_provider(
    provider: str, *, model: str | None = None, config_dir: Path | None = None
) -> EmbeddingProvider:
    """Get or create an embedder for a specific provider+model. Cached."""
    cache_key = f"{provider}:{model}" if model else provider
    if cache_key in _embedder_cache:
        return _embedder_cache[cache_key]

    provider_config = load_provider_config(provider, config_dir=config_dir)
    if provider == "openai":
        if provider_config is None:
            msg = "Cannot create OpenAI embedder — no conf.d/openai.yaml found"
            raise ValueError(msg)
        if model:
            provider_config = provider_config.model_copy(update={"model": model})
        embedder = OpenAIEmbedder(provider_config)
    elif provider == "ollama":
        if provider_config is None:
            msg = "Cannot create Ollama embedder — no conf.d/ollama.yaml found"
            raise ValueError(msg)
        if model:
            provider_config = provider_config.model_copy(update={"model": model})
        embedder = OllamaEmbedder(provider_config)
    else:
        msg = f"Unknown provider: {provider}"
        raise ValueError(msg)

    _embedder_cache[cache_key] = embedder
    return embedder
