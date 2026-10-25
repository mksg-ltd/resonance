"""Embedding provider abstraction — factory and re-exports."""

import hashlib
import json
from pathlib import Path

import yaml

from resonance.config import OpenAIProviderConfig, load_provider_config
from resonance.errors import fail

from .base import EmbeddingProvider
from .ollama import OllamaEmbedder
from .openai import OpenAIEmbedder

__all__ = ["EmbeddingProvider", "OllamaEmbedder", "OpenAIEmbedder", "create_embedder_for_name"]

# Cache by effective configuration, including credential identity
_embedder_cache: dict[str, EmbeddingProvider] = {}


def create_embedder_for_name(name: str, *, config_dir: Path | None = None) -> EmbeddingProvider:
    """Create (or return cached) embedder for a named provider config.

    Loads conf.d/{name}.yaml, reads the 'type' field, and creates the
    appropriate embedder. Results are cached by effective configuration.
    """
    provider_type, provider_config = load_provider_config(name, config_dir=config_dir)
    runtime = provider_config.model_dump(mode="json")
    if isinstance(provider_config, OpenAIProviderConfig):
        runtime["base_url"] = provider_config.effective_base_url
    secret = getattr(provider_config, "api_key", None)
    if secret:
        runtime["api_key"] = hashlib.sha256(secret.get_secret_value().encode()).hexdigest()
    key = hashlib.sha256(json.dumps([provider_type, runtime], sort_keys=True).encode()).hexdigest()
    if key in _embedder_cache:
        return _embedder_cache[key]

    if provider_type == "openai":
        embedder = OpenAIEmbedder(provider_config)
    elif provider_type == "ollama":
        embedder = OllamaEmbedder(provider_config)
    else:
        msg = f"Unknown provider type: {provider_type}"
        raise ValueError(msg)

    _embedder_cache[key] = embedder
    return embedder


def close_embedders() -> None:
    """Release cached clients after application shutdown."""
    for embedder in _embedder_cache.values():
        close = getattr(embedder, "close", None)
        if callable(close):
            close()
    _embedder_cache.clear()


def resolve_embedder(name: str) -> EmbeddingProvider:
    """Translate configuration failures without exposing raw configuration values."""
    try:
        return create_embedder_for_name(name)
    except ValueError, OSError, yaml.YAMLError:
        fail("Embedding configuration is invalid or missing", code="invalid_configuration", status=400)
