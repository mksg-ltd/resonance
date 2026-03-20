"""Tests for configuration loading."""

import os

import pytest

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
        assert settings.qdrant.url == "http://localhost:6333"
        assert settings.chunking.gap_threshold_sec == 10.0
        assert settings.chunking.min_chunk_lines == 2
        assert settings.debug is False



class TestYamlLoading:
    def test_load_from_yaml(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
qdrant:
  url: http://qdrant:6333
chunking:
  gap_threshold_sec: 8.0
debug: true
""")
        settings = load_settings(config_path=config_file)
        assert settings.qdrant.url == "http://qdrant:6333"
        assert settings.chunking.gap_threshold_sec == 8.0
        assert settings.debug is True

    def test_partial_yaml_uses_defaults(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
qdrant:
  url: http://custom:6333
""")
        settings = load_settings(config_path=config_file)
        assert settings.qdrant.url == "http://custom:6333"
        assert settings.debug is False

    def test_missing_config_uses_defaults(self, tmp_path):
        settings = load_settings(config_path=tmp_path / "nonexistent.yaml")
        assert settings.qdrant.url == "http://localhost:6333"

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
        monkeypatch.setenv("RESONANCE__DEBUG", "true")
        settings = Settings()
        assert settings.debug is True


class TestProviderConfig:
    def test_load_openai_config(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key-123")
        (tmp_path / "openai.yaml").write_text("type: openai\napi_key: ${OPENAI_API_KEY}\nmodel: text-embedding-3-large\n")

        provider_type, config = load_provider_config("openai", config_dir=tmp_path)
        assert provider_type == "openai"
        assert isinstance(config, OpenAIProviderConfig)
        assert config.api_key.get_secret_value() == "sk-test-key-123"
        assert config.model == "text-embedding-3-large"

    def test_load_ollama_config(self, tmp_path):
        (tmp_path / "ollama-bge.yaml").write_text("type: ollama\nbase_url: http://ollama:11434\nmodel: bge-m3\n")

        provider_type, config = load_provider_config("ollama-bge", config_dir=tmp_path)
        assert provider_type == "ollama"
        assert isinstance(config, OllamaProviderConfig)
        assert config.base_url == "http://ollama:11434"
        assert config.model == "bge-m3"

    def test_missing_provider_config_raises(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with pytest.raises(ValueError, match="not found"):
            load_provider_config("nonexistent", config_dir=tmp_path / "nope")

    def test_missing_type_field_raises(self, tmp_path):
        (tmp_path / "bad.yaml").write_text("model: something\n")
        with pytest.raises(ValueError, match="missing 'type' field"):
            load_provider_config("bad", config_dir=tmp_path)

    def test_unknown_type_raises(self, tmp_path):
        (tmp_path / "bad.yaml").write_text("type: pytorch\nmodel: something\n")
        with pytest.raises(ValueError, match="Unknown provider type"):
            load_provider_config("bad", config_dir=tmp_path)


class TestConfigDiscovery:
    def test_env_var_config_path(self, tmp_path, monkeypatch):
        config_file = tmp_path / "custom.yaml"
        config_file.write_text("""
qdrant:
  url: http://custom:6333
""")
        monkeypatch.setenv("RESONANCE_CONFIG", str(config_file))
        monkeypatch.chdir(tmp_path)
        settings = load_settings()
        assert settings.qdrant.url == "http://custom:6333"

    def test_local_config_yaml(self, tmp_path, monkeypatch):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
debug: true
""")
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("RESONANCE_CONFIG", raising=False)
        settings = load_settings()
        assert settings.debug is True
