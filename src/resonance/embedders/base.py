"""Embedding provider protocol — the contract all providers implement."""

from typing import Protocol


class EmbeddingProvider(Protocol):
    """Protocol for embedding text into vectors."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts into vectors."""
        ...

    @property
    def dimensions(self) -> int:
        """Vector dimensionality for this provider/model."""
        ...

    @property
    def model_name(self) -> str:
        """Model identifier (stored in collection metadata)."""
        ...

    @property
    def provider_name(self) -> str:
        """Provider identifier (e.g., 'openai', 'ollama')."""
        ...
