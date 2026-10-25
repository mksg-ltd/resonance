"""Tests for embedding provider abstraction."""

from unittest.mock import MagicMock, patch

import httpx

from resonance.config import OllamaProviderConfig, OpenAIProviderConfig
from resonance.embedders import OpenAIEmbedder, OllamaEmbedder


class TestOpenAIEmbedder:
    def test_embed_returns_vectors(self):
        config = OpenAIProviderConfig(api_key="sk-test", model="text-embedding-3-small")
        embedder = OpenAIEmbedder(config)

        mock_response = MagicMock()
        mock_response.data = [
            MagicMock(embedding=[0.1, 0.2, 0.3]),
            MagicMock(embedding=[0.4, 0.5, 0.6]),
        ]
        embedder._client.embeddings.create = MagicMock(return_value=mock_response)

        result = embedder.embed(["hello", "world"])
        assert len(result) == 2
        assert result[0] == [0.1, 0.2, 0.3]
        assert result[1] == [0.4, 0.5, 0.6]

    def test_dimensions_known_model(self):
        config = OpenAIProviderConfig(api_key="sk-test", model="text-embedding-3-small")
        embedder = OpenAIEmbedder(config)
        assert embedder.dimensions == 1536

    def test_dimensions_large_model(self):
        config = OpenAIProviderConfig(api_key="sk-test", model="text-embedding-3-large")
        embedder = OpenAIEmbedder(config)
        assert embedder.dimensions == 3072

    def test_dimensions_unknown_model_defaults(self):
        config = OpenAIProviderConfig(api_key="sk-test", model="some-future-model")
        embedder = OpenAIEmbedder(config)
        assert embedder.dimensions == 1536

    def test_dimensions_override(self):
        config = OpenAIProviderConfig(api_key="sk-test", model="custom-model", dimensions=768)
        embedder = OpenAIEmbedder(config)
        assert embedder.dimensions == 768

    def test_base_url(self):
        config = OpenAIProviderConfig(model="custom", base_url="http://localhost:8085/v1")
        embedder = OpenAIEmbedder(config)
        assert embedder._client.base_url.host == "localhost"

    def test_properties(self):
        config = OpenAIProviderConfig(api_key="sk-test", model="text-embedding-3-small")
        embedder = OpenAIEmbedder(config)
        assert embedder.model_name == "text-embedding-3-small"
        assert embedder.provider_name == "openai"


class TestOllamaEmbedder:
    def test_embed_returns_vectors(self):
        config = OllamaProviderConfig(base_url="http://localhost:11434", model="nomic-embed-text")
        embedder = OllamaEmbedder(config)

        mock_response = httpx.Response(
            200,
            json={"embeddings": [[0.1, 0.2], [0.3, 0.4]]},
            request=httpx.Request("POST", "http://localhost:11434/api/embed"),
        )
        with patch.object(httpx, "post", return_value=mock_response):
            result = embedder.embed(["hello", "world"])

        assert len(result) == 2
        assert result[0] == [0.1, 0.2]

    def test_dimensions_known_model(self):
        config = OllamaProviderConfig(model="nomic-embed-text")
        embedder = OllamaEmbedder(config)
        assert embedder.dimensions == 768

    def test_dimensions_mxbai(self):
        config = OllamaProviderConfig(model="mxbai-embed-large")
        embedder = OllamaEmbedder(config)
        assert embedder.dimensions == 1024

    def test_properties(self):
        config = OllamaProviderConfig(model="nomic-embed-text")
        embedder = OllamaEmbedder(config)
        assert embedder.model_name == "nomic-embed-text"
        assert embedder.provider_name == "ollama"


def test_openai_response_indices_preserve_input_order():
    from types import SimpleNamespace

    embedder = OpenAIEmbedder(OpenAIProviderConfig(api_key="sk-test"))
    embedder._client.embeddings.create = MagicMock(
        return_value=SimpleNamespace(
            data=[
                SimpleNamespace(index=1, embedding=[0.0, 1.0]),
                SimpleNamespace(index=0, embedding=[1.0, 0.0]),
            ]
        )
    )
    assert embedder.embed(["first", "second"]) == [[1.0, 0.0], [0.0, 1.0]]
    embedder.close()


def test_explicit_openai_endpoint_takes_precedence_over_sdk_environment(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://environment.test/v1")
    embedder = OpenAIEmbedder(OpenAIProviderConfig(base_url="https://configured.test/v1"))
    assert embedder.profile["endpoint"] == str(embedder._client.base_url).rstrip("/") == "https://configured.test/v1"
    embedder.close()
