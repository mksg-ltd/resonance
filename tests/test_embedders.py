"""Tests for embedding provider abstraction."""

from unittest.mock import MagicMock, patch

import httpx

from resonance.config import OllamaProviderConfig, OpenAIProviderConfig, Settings, load_settings
from resonance.embedders import OpenAIEmbedder, OllamaEmbedder, create_embedder


class TestOpenAIEmbedder:
    def test_embed_returns_vectors(self):
        config = OpenAIProviderConfig(api_key="sk-test", model="text-embedding-3-small")
        embedder = OpenAIEmbedder(config)

        # Mock the OpenAI client's embeddings.create
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
        embedder._client.embeddings.create.assert_called_once_with(
            model="text-embedding-3-small", input=["hello", "world"]
        )

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


class TestCreateEmbedder:
    def test_creates_openai_embedder(self, tmp_path):
        conf_d = tmp_path / "conf.d"
        conf_d.mkdir()
        (conf_d / "openai.yaml").write_text("api_key: sk-test\nmodel: text-embedding-3-small\n")

        settings = Settings(embedding={"provider": "openai"})
        embedder = create_embedder(settings, config_dir=conf_d)
        assert isinstance(embedder, OpenAIEmbedder)
        assert embedder.model_name == "text-embedding-3-small"

    def test_creates_ollama_embedder(self, tmp_path):
        conf_d = tmp_path / "conf.d"
        conf_d.mkdir()
        (conf_d / "ollama.yaml").write_text("base_url: http://localhost:11434\nmodel: nomic-embed-text\n")

        settings = Settings(embedding={"provider": "ollama"})
        embedder = create_embedder(settings, config_dir=conf_d)
        assert isinstance(embedder, OllamaEmbedder)
        assert embedder.model_name == "nomic-embed-text"

    def test_raises_for_missing_provider_config(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        settings = Settings(embedding={"provider": "openai"})
        try:
            create_embedder(settings, config_dir=tmp_path / "nonexistent")
            msg = "Should have raised ValueError"
            raise AssertionError(msg)
        except ValueError as e:
            assert "no conf.d/openai.yaml found" in str(e)

    def test_raises_for_unknown_provider(self, tmp_path):
        settings = Settings(embedding={"provider": "unknown"})
        try:
            create_embedder(settings, config_dir=tmp_path)
            msg = "Should have raised ValueError"
            raise AssertionError(msg)
        except ValueError as e:
            assert "Unknown embedding provider" in str(e)
