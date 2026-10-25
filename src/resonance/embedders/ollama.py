"""Ollama embedding provider — local models via Ollama API."""

from typing import Any

import httpx

from resonance.config import OllamaProviderConfig

KNOWN_DIMENSIONS: dict[str, int] = {
    "nomic-embed-text": 768,
    "mxbai-embed-large": 1024,
    "all-minilm": 384,
    "snowflake-arctic-embed": 1024,
}


class OllamaEmbedder:
    """Embed text using a local Ollama instance."""

    def __init__(self, config: OllamaProviderConfig) -> None:
        self._base_url = config.base_url.rstrip("/")
        self._model = config.model
        self._dimensions = config.dimensions or KNOWN_DIMENSIONS.get(config.model, 768)
        self._profile = {
            "provider": "ollama",
            "model": config.model,
            "dimensions": self._dimensions,
            "endpoint": self._base_url,
            "dimensions_verified": bool(config.dimensions or config.model in KNOWN_DIMENSIONS),
            "revision": config.revision,
        }

    @property
    def profile(self) -> dict[str, Any]:
        return dict(self._profile)

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts using Ollama's /api/embed endpoint."""
        response = httpx.post(
            f"{self._base_url}/api/embed",
            json={"model": self._model, "input": texts},
            timeout=120.0,
        )
        response.raise_for_status()
        return response.json()["embeddings"]

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def provider_name(self) -> str:
        return "ollama"
