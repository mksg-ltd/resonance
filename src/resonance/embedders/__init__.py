"""Embedding provider abstraction — factory and re-exports."""

from pathlib import Path

from resonance.config import load_provider_config

from .base import EmbeddingProvider
from .ollama import OllamaEmbedder
from .openai import OpenAIEmbedder

__all__ = ["EmbeddingProvider", "OllamaEmbedder", "OpenAIEmbedder", "create_embedder_for_name"]

# Cache of embedders by config name
_embedder_cache: dict[str, EmbeddingProvider] = {}


def create_embedder_for_name(name: str, *, config_dir: Path | None = None) -> EmbeddingProvider:
    """Create (or return cached) embedder for a named provider config.

    Loads conf.d/{name}.yaml, reads the 'type' field, and creates the
    appropriate embedder. Results are cached by name.
    """
    if name in _embedder_cache:
        return _embedder_cache[name]

    provider_type, provider_config = load_provider_config(name, config_dir=config_dir)

    if provider_type == "openai":
        embedder = OpenAIEmbedder(provider_config)
    elif provider_type == "ollama":
        embedder = OllamaEmbedder(provider_config)
    else:
        msg = f"Unknown provider type: {provider_type}"
        raise ValueError(msg)

    _embedder_cache[name] = embedder
    return embedder
