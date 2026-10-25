"""Tests for configuration loading."""

from resonance.config import Settings


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


def test_navidrome_dotenv_preserves_quoted_and_dollar_credentials(tmp_path, monkeypatch):
    from resonance.config import NavidromeConfig

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("NAVIDROME_USER_PASSWORD", raising=False)
    (tmp_path / ".env").write_text('NAVIDROME_USER_PASSWORD="literal$dollar and spaces"\n')
    settings = NavidromeConfig()
    assert settings.user_password.get_secret_value() == "literal$dollar and spaces"
    assert "literal" not in settings.model_dump_json()
