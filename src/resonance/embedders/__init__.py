"""Embedding provider abstraction — factory and re-exports."""

import hashlib
import json
import os

import yaml
from pydantic import SecretStr

from resonance.config import EmbeddingRuntimeConfig, OllamaProviderConfig, OpenAIProviderConfig
from resonance.embedding_profiles import EmbeddingProfile, get_embedding_profile
from resonance.errors import fail

from .base import EmbeddingProvider
from .ollama import OllamaEmbedder
from .openai import OpenAIEmbedder

__all__ = ["EmbeddingProvider", "OllamaEmbedder", "OpenAIEmbedder", "create_embedder_for_profile"]

# Cache by effective configuration, including credential identity
_embedder_cache: dict[str, EmbeddingProvider] = {}


def create_embedder_for_profile(
    profile_id: str,
    runtime_config: EmbeddingRuntimeConfig,
) -> EmbeddingProvider:
    """Create (or return cached) embedder for a catalog profile and runtime endpoint."""
    profile = get_embedding_profile(profile_id)
    provider_config = _provider_config(profile, runtime_config)
    runtime = provider_config.model_dump(mode="json")
    if isinstance(provider_config, OpenAIProviderConfig):
        runtime["base_url"] = provider_config.effective_base_url
    secret = getattr(provider_config, "api_key", None)
    if secret:
        runtime["api_key"] = hashlib.sha256(secret.get_secret_value().encode()).hexdigest()
    key = hashlib.sha256(json.dumps([profile_id, profile.model_dump(), runtime], sort_keys=True).encode()).hexdigest()
    if key in _embedder_cache:
        return _embedder_cache[key]

    if profile.protocol == "openai-compatible":
        embedder = OpenAIEmbedder(provider_config)
    elif profile.protocol == "ollama":
        embedder = OllamaEmbedder(provider_config)
    else:
        msg = f"Unsupported embedding protocol: {profile.protocol}"
        raise ValueError(msg)

    _embedder_cache[key] = embedder
    return embedder


def _provider_config(
    profile: EmbeddingProfile,
    runtime: EmbeddingRuntimeConfig,
) -> OpenAIProviderConfig | OllamaProviderConfig:
    if profile.protocol == "ollama":
        return OllamaProviderConfig(
            base_url=runtime.base_url or "http://localhost:11434",
            model=profile.model_id,
            dimensions=profile.dimensions,
            revision=profile.revision,
        )

    base_url = runtime.base_url
    if not base_url and profile.model_id != "text-embedding-3-large":
        base_url = os.environ.get("OPENAI_BASE_URL")
        if not base_url:
            msg = f"Set RESONANCE__EMBEDDING__BASE_URL for profile '{profile.model_id}'"
            raise ValueError(msg)
    api_key = runtime.api_key
    if api_key is None or not api_key.get_secret_value():
        api_key = SecretStr(os.environ.get("OPENAI_API_KEY", "dummy"))
    return OpenAIProviderConfig(
        api_key=api_key,
        model=profile.model_id,
        base_url=base_url,
        dimensions=profile.dimensions,
        revision=profile.revision,
    )


def close_embedders() -> None:
    """Release cached clients after application shutdown."""
    for embedder in _embedder_cache.values():
        close = getattr(embedder, "close", None)
        if callable(close):
            close()
    _embedder_cache.clear()


def resolve_embedder(profile_id: str, runtime_config: EmbeddingRuntimeConfig) -> EmbeddingProvider:
    """Translate configuration failures without exposing raw configuration values."""
    try:
        return create_embedder_for_profile(profile_id, runtime_config)
    except ValueError as error:
        fail(str(error), code="invalid_configuration", status=400)
    except OSError, TypeError, yaml.YAMLError:
        fail("Embedding configuration is invalid or missing", code="invalid_configuration", status=400)
