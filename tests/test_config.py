"""Tests for configuration loading."""

import pytest

from resonance.config import (
    OllamaProviderConfig,
    OpenAIProviderConfig,
    Settings,
    load_provider_config,
)


class TestSettingsDefaults:
    def test_default_settings(self):
        settings = Settings()
        assert settings.qdrant.url == "http://localhost:6333"
        assert settings.chunking.gap_threshold_sec == 10.0
        assert settings.chunking.min_chunk_lines == 2
        assert settings.debug is False
        assert settings.serve_docs is False

    def test_env_var_overrides(self, monkeypatch):
        monkeypatch.setenv("RESONANCE__DEBUG", "true")
        monkeypatch.setenv("RESONANCE__SERVE_DOCS", "true")
        monkeypatch.setenv("RESONANCE__QDRANT__URL", "http://qdrant:6333")
        settings = Settings()
        assert settings.debug is True
        assert settings.serve_docs is True
        assert settings.qdrant.url == "http://qdrant:6333"

    def test_chunking_env_vars(self, monkeypatch):
        monkeypatch.setenv("RESONANCE__CHUNKING__GAP_THRESHOLD_SEC", "8.0")
        monkeypatch.setenv("RESONANCE__CHUNKING__MIN_CHUNK_LINES", "3")
        settings = Settings()
        assert settings.chunking.gap_threshold_sec == 8.0
        assert settings.chunking.min_chunk_lines == 3


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


def test_navidrome_dotenv_preserves_quoted_and_dollar_credentials(tmp_path, monkeypatch):
    from resonance.config import NavidromeConfig

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("NAVIDROME_USER_PASSWORD", raising=False)
    (tmp_path / ".env").write_text('NAVIDROME_USER_PASSWORD="literal$dollar and spaces"\n')
    settings = NavidromeConfig()
    assert settings.user_password.get_secret_value() == "literal$dollar and spaces"
    assert "literal" not in settings.model_dump_json()
