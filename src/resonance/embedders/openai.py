"""OpenAI embedding provider."""

from typing import Any

from openai import OpenAI

from resonance.config import OpenAIProviderConfig

KNOWN_DIMENSIONS: dict[str, int] = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}


class OpenAIEmbedder:
    """Embed text using OpenAI's embedding API (or any OpenAI-compatible server)."""

    def __init__(self, config: OpenAIProviderConfig) -> None:
        self._client = OpenAI(api_key=config.api_key.get_secret_value(), base_url=config.effective_base_url)
        self._model = config.model
        self._dimensions = config.dimensions or KNOWN_DIMENSIONS.get(config.model, 1536)
        self._profile = {
            "provider": "openai",
            "model": config.model,
            "dimensions": self._dimensions,
            "endpoint": str(self._client.base_url).rstrip("/"),
            "dimensions_verified": bool(config.dimensions or config.model in KNOWN_DIMENSIONS),
            "revision": config.revision,
        }

    @property
    def profile(self) -> dict[str, Any]:
        """Non-secret vector-space identity; dimensions describe expected output."""
        return dict(self._profile)

    def close(self) -> None:
        self._client.close()

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts using OpenAI API."""
        response = self._client.embeddings.create(model=self._model, input=texts)
        items = list(response.data)
        indices = [getattr(item, "index", None) for item in items]
        if any(type(index) is int for index in indices):
            if any(type(index) is not int for index in indices) or sorted(indices) != list(range(len(texts))):
                msg = "Embedding response indices are inconsistent"
                raise ValueError(msg)
            items.sort(key=lambda item: item.index)
        return [item.embedding for item in items]

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def provider_name(self) -> str:
        return "openai"
