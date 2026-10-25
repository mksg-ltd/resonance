"""Shared API authentication boundary tests."""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from resonance.app import cli, create_app, dev
from resonance.config import Settings


def test_debug_runner_binds_to_loopback(monkeypatch):
    monkeypatch.setenv("RESONANCE__DEBUG", "false")
    monkeypatch.setenv("RESONANCE__SERVE_DOCS", "false")
    with patch("resonance.app.uvicorn.run") as run:
        dev()

    assert run.call_args.kwargs["host"] == "127.0.0.1"
    assert run.call_args.kwargs["proxy_headers"] is False


def test_server_runner_uses_only_configured_proxy_ips(monkeypatch):
    monkeypatch.setenv("RESONANCE__TRUSTED_PROXY_IPS", "10.10.0.7")
    with patch("resonance.app.uvicorn.run") as run:
        cli()

    assert run.call_args.kwargs["forwarded_allow_ips"] == "10.10.0.7"


def test_protected_data_routes_reject_missing_auth_before_side_effects(monkeypatch):
    settings = Settings(debug=True, navidrome={"base_url": "https://music.test"}, _env_file=None)
    app = create_app(settings)
    qdrant = MagicMock()
    monkeypatch.setattr("resonance.app.QdrantClient", lambda **_: qdrant)
    routes = [
        ("get", "/api/config", {}),
        ("get", "/api/collections", {}),
        ("delete", "/api/collections/guessed", {}),
        ("post", "/api/search", {"json": {"query": "theme", "collection": "guessed"}}),
        ("post", "/api/ingest", {"json": {"library_id": "1"}}),
        ("get", "/api/navidrome/libraries", {}),
        ("post", "/api/navidrome/playlists", {"json": {}}),
    ]
    with TestClient(app, base_url="http://localhost:8000") as client:
        for method, path, kwargs in routes:
            response = getattr(client, method)(path, **kwargs)
            assert response.status_code == 401, (method, path, response.text)
    qdrant.get_collections.assert_not_called()
    qdrant.retrieve.assert_not_called()
    qdrant.delete_collection.assert_not_called()
