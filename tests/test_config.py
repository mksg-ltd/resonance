"""Tests for configuration loading."""

import os

from resonance.config import (
    OllamaProviderConfig,
    OpenAIProviderConfig,
    Settings,
    load_provider_config,
    load_settings,
)


class TestSettingsDefaults:
    def test_default_settings(self):
        settings = Settings()
        assert settings.embedding.provider == "openai"
        assert settings.qdrant.url == "http://localhost:6333"
        assert settings.qdrant.collection == "lyrics"
        assert settings.chunking.gap_threshold_sec == 10.0
        assert settings.chunking.min_chunk_lines == 2
        assert settings.server.port == 8000
        assert settings.server.debug is False

    def test_jellyfin_defaults_to_none(self):
        settings = Settings()
        assert settings.jellyfin.url is None
        assert settings.jellyfin.api_key is None


class TestYamlLoading:
    def test_load_from_yaml(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
embedding:
  provider: ollama
qdrant:
  url: http://qdrant:6333
  collection: test_lyrics
chunking:
  gap_threshold_sec: 8.0
server:
  debug: true
""")
        settings = load_settings(config_path=config_file)
        assert settings.embedding.provider == "ollama"
        assert settings.qdrant.url == "http://qdrant:6333"
        assert settings.qdrant.collection == "test_lyrics"
        assert settings.chunking.gap_threshold_sec == 8.0
        assert settings.server.debug is True

    def test_partial_yaml_uses_defaults(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
embedding:
  provider: ollama
""")
        settings = load_settings(config_path=config_file)
        assert settings.embedding.provider == "ollama"
        assert settings.qdrant.url == "http://localhost:6333"
        assert settings.server.port == 8000

    def test_missing_config_uses_defaults(self, tmp_path):
        settings = load_settings(config_path=tmp_path / "nonexistent.yaml")
        assert settings.embedding.provider == "openai"

    def test_env_var_expansion_in_yaml(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TEST_QDRANT_URL", "http://custom:6333")
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
qdrant:
  url: ${TEST_QDRANT_URL}
""")
        settings = load_settings(config_path=config_file)
        assert settings.qdrant.url == "http://custom:6333"


class TestEnvVarOverride:
    def test_env_var_overrides_yaml(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RESONANCE__QDRANT__URL", "http://env-qdrant:6333")
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
qdrant:
  url: http://yaml-qdrant:6333
""")
        settings = load_settings(config_path=config_file)
        assert settings.qdrant.url == "http://env-qdrant:6333"

    def test_env_var_overrides_default(self, monkeypatch):
        monkeypatch.setenv("RESONANCE__SERVER__PORT", "9000")
        settings = Settings()
        assert settings.server.port == 9000


class TestProviderConfig:
    def test_load_openai_config(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key-123")
        conf_d = tmp_path / "conf.d"
        conf_d.mkdir()
        (conf_d / "openai.yaml").write_text("""
api_key: ${OPENAI_API_KEY}
model: text-embedding-3-large
""")
        config = load_provider_config("openai", config_dir=conf_d)
        assert isinstance(config, OpenAIProviderConfig)
        assert config.api_key.get_secret_value() == "sk-test-key-123"
        assert config.model == "text-embedding-3-large"

    def test_load_ollama_config(self, tmp_path):
        conf_d = tmp_path / "conf.d"
        conf_d.mkdir()
        (conf_d / "ollama.yaml").write_text("""
base_url: http://ollama:11434
model: mxbai-embed-large
""")
        config = load_provider_config("ollama", config_dir=conf_d)
        assert isinstance(config, OllamaProviderConfig)
        assert config.base_url == "http://ollama:11434"
        assert config.model == "mxbai-embed-large"

    def test_missing_provider_config_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        config = load_provider_config("openai", config_dir=tmp_path / "nonexistent")
        assert config is None

    def test_unknown_provider_returns_none(self, tmp_path):
        conf_d = tmp_path / "conf.d"
        conf_d.mkdir()
        (conf_d / "unknown.yaml").write_text("key: value")
        config = load_provider_config("unknown", config_dir=conf_d)
        assert config is None


class TestConfigDiscovery:
    def test_env_var_config_path(self, tmp_path, monkeypatch):
        config_file = tmp_path / "custom.yaml"
        config_file.write_text("""
embedding:
  provider: ollama
""")
        monkeypatch.setenv("RESONANCE_CONFIG", str(config_file))
        monkeypatch.chdir(tmp_path)
        settings = load_settings()
        assert settings.embedding.provider == "ollama"

    def test_local_config_yaml(self, tmp_path, monkeypatch):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
server:
  port: 9999
""")
        monkeypatch.chdir(tmp_path)
        # Clear any RESONANCE_CONFIG env var
        monkeypatch.delenv("RESONANCE_CONFIG", raising=False)
        settings = load_settings()
        assert settings.server.port == 9999
