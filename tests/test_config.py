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


def test_admin_user_uses_the_exact_environment_key(monkeypatch):
    monkeypatch.setenv("RESONANCE_ADMIN_USER", "owner")
    monkeypatch.delenv("RESONANCE__ADMIN_USER", raising=False)
    assert Settings(_env_file=None).admin_user == "owner"


def test_admin_user_can_be_set_programmatically():
    assert Settings(admin_user="owner", _env_file=None).admin_user == "owner"


def test_navidrome_configuration_contains_server_settings_not_user_credentials(tmp_path, monkeypatch):
    from resonance.config import NavidromeConfig

    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        'NAVIDROME_BASE_URL="https://music.test"\n'
        'NAVIDROME_USER_ID="legacy-user"\n'
        'NAVIDROME_USER_PASSWORD="legacy-secret"\n'
    )
    settings = NavidromeConfig()
    assert settings.base_url == "https://music.test"
    assert not hasattr(settings, "user_id")
    assert not hasattr(settings, "user_password")
    assert "legacy-secret" not in settings.model_dump_json()
