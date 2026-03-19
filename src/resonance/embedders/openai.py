"""OpenAI embedding provider."""

from openai import OpenAI

from resonance.config import OpenAIProviderConfig

KNOWN_DIMENSIONS: dict[str, int] = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}


class OpenAIEmbedder:
    """Embed text using OpenAI's embedding API."""

    def __init__(self, config: OpenAIProviderConfig) -> None:
        self._client = OpenAI(api_key=config.api_key.get_secret_value())
        self._model = config.model
        self._dimensions = KNOWN_DIMENSIONS.get(config.model, 1536)

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts using OpenAI API."""
        response = self._client.embeddings.create(model=self._model, input=texts)
        return [item.embedding for item in response.data]

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def provider_name(self) -> str:
        return "openai"
