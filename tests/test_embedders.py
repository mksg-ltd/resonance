"""Tests for embedding provider abstraction."""

from unittest.mock import MagicMock, patch

import httpx

from resonance.config import OllamaProviderConfig, OpenAIProviderConfig
from resonance.embedders import OpenAIEmbedder, OllamaEmbedder, create_embedder_for_name


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


class TestCreateEmbedderForName:
    def test_creates_openai_embedder(self, tmp_path):
        (tmp_path / "my-openai.yaml").write_text("type: openai\napi_key: sk-test\nmodel: text-embedding-3-small\n")

        embedder = create_embedder_for_name("my-openai", config_dir=tmp_path)
        assert isinstance(embedder, OpenAIEmbedder)
        assert embedder.model_name == "text-embedding-3-small"

    def test_creates_ollama_embedder(self, tmp_path):
        (tmp_path / "my-ollama.yaml").write_text("type: ollama\nbase_url: http://localhost:11434\nmodel: bge-m3\n")

        embedder = create_embedder_for_name("my-ollama", config_dir=tmp_path)
        assert isinstance(embedder, OllamaEmbedder)
        assert embedder.model_name == "bge-m3"

    def test_creates_tei_embedder_via_openai_type(self, tmp_path):
        (tmp_path / "vyakyarth.yaml").write_text(
            "type: openai\nmodel: krutrim-ai-labs/Vyakyarth\nbase_url: http://localhost:8085/v1\ndimensions: 768\n"
        )

        embedder = create_embedder_for_name("vyakyarth", config_dir=tmp_path)
        assert isinstance(embedder, OpenAIEmbedder)
        assert embedder.dimensions == 768
        assert embedder.model_name == "krutrim-ai-labs/Vyakyarth"

    def test_raises_for_missing_config(self, tmp_path):
        try:
            create_embedder_for_name("nonexistent", config_dir=tmp_path)
            msg = "Should have raised ValueError"
            raise AssertionError(msg)
        except ValueError as e:
            assert "not found" in str(e)

    def test_raises_for_missing_type_field(self, tmp_path):
        (tmp_path / "bad.yaml").write_text("model: something\n")

        try:
            create_embedder_for_name("bad", config_dir=tmp_path)
            msg = "Should have raised ValueError"
            raise AssertionError(msg)
        except ValueError as e:
            assert "missing 'type' field" in str(e)

    def test_raises_for_unknown_type(self, tmp_path):
        (tmp_path / "bad.yaml").write_text("type: pytorch\nmodel: something\n")

        try:
            create_embedder_for_name("bad", config_dir=tmp_path)
            msg = "Should have raised ValueError"
            raise AssertionError(msg)
        except ValueError as e:
            assert "Unknown provider type" in str(e)

    def test_caches_by_name(self, tmp_path):
        (tmp_path / "cached.yaml").write_text("type: ollama\nmodel: nomic-embed-text\n")

        e1 = create_embedder_for_name("cached", config_dir=tmp_path)
        e2 = create_embedder_for_name("cached", config_dir=tmp_path)
        assert e1 is e2


def test_effective_config_change_invalidates_cache(tmp_path):
    config = tmp_path / "mutable.yaml"
    config.write_text("type: ollama\nmodel: nomic-embed-text\n")
    first = create_embedder_for_name("mutable", config_dir=tmp_path)
    config.write_text("type: ollama\nmodel: mxbai-embed-large\n")
    second = create_embedder_for_name("mutable", config_dir=tmp_path)
    assert first is not second and second.dimensions == 1024


def test_openai_response_indices_preserve_input_order():
    from types import SimpleNamespace
    embedder = OpenAIEmbedder(OpenAIProviderConfig(api_key="sk-test"))
    embedder._client.embeddings.create = MagicMock(return_value=SimpleNamespace(data=[
        SimpleNamespace(index=1, embedding=[0.0, 1.0]),
        SimpleNamespace(index=0, embedding=[1.0, 0.0]),
    ]))
    assert embedder.embed(["first", "second"]) == [[1.0, 0.0], [0.0, 1.0]]
    embedder.close()


def test_explicit_openai_endpoint_takes_precedence_over_sdk_environment(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://environment.test/v1")
    embedder = OpenAIEmbedder(OpenAIProviderConfig(base_url="https://configured.test/v1"))
    assert embedder.profile["endpoint"] == str(embedder._client.base_url).rstrip("/") == "https://configured.test/v1"
    embedder.close()
