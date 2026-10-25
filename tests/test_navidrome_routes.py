"""CLI/HTTP parity through real source/application/Qdrant/SQLite paths."""

import json
from dataclasses import asdict
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient

from resonance import playlists
from resonance.app import create_app
from resonance.config import Settings
from resonance.models import Library
from tests.test_indexing import FixtureEmbedder
from tests.test_save_operations import SaveServer, selection


@pytest.fixture
def native(tmp_path, monkeypatch):
    server = SaveServer()
    qdrant = QdrantClient(":memory:")
    embedder = FixtureEmbedder()
    source = server.client()
    original = source._http

    def transport(request):
        if request.url.path.endswith("getLyricsBySongId.view"):
            return server.ok(
                lyricsList={
                    "structuredLyrics": [
                        {
                            "synced": True,
                            "lang": "xxx",
                            "line": [
                                {"start": 0, "value": "[Verse] I fold a paper kite"},
                                {"start": 2000, "value": "And let it find the light"},
                            ],
                        }
                    ]
                }
            )
        return server(request)

    http = httpx.Client(transport=httpx.MockTransport(transport))
    source._http = http
    settings = Settings(
        debug=True,
        admin_user="operator",
        navidrome=source.config,
        journal_path=tmp_path / "operations.sqlite3",
        _env_file=None,
    )
    app = create_app(settings)
    app.state.navidrome = source
    monkeypatch.setattr("resonance.app.QdrantClient", lambda **_: qdrant)
    monkeypatch.setattr("resonance.embedders.resolve_embedder", lambda *_: embedder)
    login_client = MagicMock()
    login_client.libraries.return_value = [Library("2", "English")]
    monkeypatch.setattr("resonance.routes.auth.NavidromeClient", lambda *_: login_client)
    with TestClient(app, base_url="http://localhost:8000") as client:
        login = client.post(
            "/api/auth/login",
            json={"username": "operator", "password": "test-secret"},
            headers={"Origin": "http://localhost:8000"},
        )
        assert login.status_code == 200
        assert "access_token" not in login.json()
        assert "httponly" in login.headers["set-cookie"].lower()
        server.calls.clear()
        yield client, app, server, source, embedder, qdrant, settings
    http.close()
    original.close()


def auth():
    return {"Origin": "http://localhost:8000"}


def test_token_exchange_uses_bearer_auth_and_logout_revokes_its_session(native):
    client, *_ = native
    response = client.post("/api/auth/token", json={"username": "operator", "password": "test-secret"})
    assert response.status_code == 200
    token = response.json()["access_token"]
    bearer = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/config", headers=bearer).status_code == 200
    assert client.post("/api/auth/logout", headers=bearer).status_code == 204
    assert client.get("/api/config", headers=bearer).status_code == 401


def test_regular_user_uses_their_own_library_grants_and_playlist_identity(native, monkeypatch):
    client, app, server, _source, _embedder, _qdrant, _settings = native
    indexed = client.post(
        "/api/ingest",
        headers=auth(),
        json={"provider": "fixture", "library_id": "2", "collection": "admin-library"},
    )
    assert indexed.status_code == 200
    del app.state.navidrome

    def user_source(config, credentials):
        server.owner = credentials.username
        return server.client(username=credentials.username)

    monkeypatch.setattr("resonance.routes.auth.NavidromeClient", user_source)
    login = client.post(
        "/api/auth/login",
        headers={"Origin": "http://localhost:8000"},
        json={"username": "listener", "password": "test-secret"},
    )
    assert login.status_code == 200
    assert login.json()["is_admin"] is False
    assert login.json()["libraries"] == [{"id": "3", "name": "Restricted"}]
    assert client.get("/api/navidrome/libraries", headers=auth()).status_code == 403
    assert client.get("/api/collections", headers=auth()).json() == []
    guessed = client.post(
        "/api/search",
        headers=auth(),
        json={"query": "hidden library", "collection": "admin-library"},
    )
    assert guessed.status_code == 404

    saved = client.post(
        "/api/navidrome/playlists",
        headers=auth(),
        json=body(operation_id="listener-save", library_id="3", song_ids=["one", "two"]),
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["status"] == "verified"
    assert server.owner == "listener"
    assert server.created[0]["song_ids"] == ["one", "two"]


def test_cookie_mutations_reject_cross_site_origin(native):
    client, *_ = native
    response = client.post(
        "/api/ingest",
        json={"provider": "fixture", "library_id": "2"},
        headers={"Origin": "http://attacker.invalid"},
    )
    assert response.status_code == 403


def body(**kwargs):
    return {**asdict(selection()), **kwargs}


def test_http_full_native_flow_and_cli_same_key_parity(native, monkeypatch, capsys):
    client, app, server, source, embedder, qdrant, settings = native
    assert client.get("/api/navidrome/connection", headers=auth()).json()["server_type"] == "navidrome"
    assert client.get("/api/navidrome/libraries", headers=auth()).json()[0]["id"] == "2"
    assert len(client.get("/api/navidrome/tracks?library_id=2&limit=2", headers=auth()).json()) == 2
    assert (
        client.get("/api/navidrome/lyrics?library_id=2&song_id=one", headers=auth()).json()["lyrics_status"] == "synced"
    )
    indexed = client.post(
        "/api/ingest", headers=auth(), json={"provider": "fixture", "library_id": "2", "collection": "native"}
    )
    assert indexed.status_code == 200 and indexed.json()["tracks_processed"] == 3, indexed.text
    hits = client.post("/api/search", headers=auth(), json={"query": "paper stars", "collection": "native", "limit": 3})
    assert hits.status_code == 200
    ids = [hit["song_id"] for hit in hits.json()["results"]]
    saved = client.post("/api/navidrome/playlists", headers=auth(), json=body(song_ids=ids))
    assert saved.status_code == 200 and saved.json()["status"] == "verified"
    assert server.created[0]["song_ids"] == ids
    calls = len(embedder.calls)
    monkeypatch.setattr(playlists, "Settings", lambda: settings)
    monkeypatch.setattr(playlists, "NavidromeClient", lambda *_: source)
    monkeypatch.setattr(playlists, "prompt_navidrome_credentials", lambda: source.credentials)
    monkeypatch.setattr(
        "sys.argv",
        [
            "resonance-playlist",
            "create",
            "--operation-id",
            "operation-1",
            "--library",
            "2",
            "--name",
            "Paper Stars",
            *[value for item in ids for value in ("--song", item)],
        ],
    )
    playlists.main()
    assert json.loads(capsys.readouterr().out)["status"] == "verified"
    assert len(server.created) == 1 and len(embedder.calls) == calls
    conflict = client.post("/api/navidrome/playlists", headers=auth(), json=body(song_ids=list(reversed(ids))))
    assert conflict.status_code == 409 and conflict.json()["code"] == "operation_conflict"
    status = client.get("/api/navidrome/operations/operation-1?library_id=2", headers=auth())
    assert status.json()["status"] == "verified"


def test_unauthorized_and_unconfigured_requests_make_no_external_calls_or_journal(native):
    client, app, server, source, embedder, qdrant, settings = native
    unauthenticated = TestClient(client.app, base_url="http://localhost:8000")
    for method, path, kwargs in [
        ("get", "/api/navidrome/connection", {}),
        ("get", "/api/navidrome/operations/one?library_id=2", {}),
        ("post", "/api/navidrome/playlists", {"json": body()}),
        ("post", "/api/ingest", {"json": {"provider": "fixture", "library_id": "2"}}),
    ]:
        assert getattr(unauthenticated, method)(path, **kwargs).status_code == 401
        assert (
            getattr(unauthenticated, method)(path, headers={"Authorization": "Bearer wrong"}, **kwargs).status_code
            == 401
        )
    assert not server.calls and not settings.journal_path.exists() and not embedder.calls
    app.state.auth_runtime.admin_user = None
    assert client.post("/api/ingest", json={"provider": "fixture", "library_id": "2"}).status_code == 403
    assert not server.calls
    assert client.get("/api/navidrome/libraries", headers=auth()).status_code == 403
    config = client.get("/api/config").text
    assert "test-secret" not in config and "operator-token" not in config and "music.test" not in config


def test_invalid_stale_empty_and_dependency_errors_do_not_create(native):
    client, app, server, source, embedder, qdrant, settings = native
    for patch in (
        {"song_ids": []},
        {"song_ids": ["one", "one"]},
        {"song_ids": ["gone"]},
        {"public": True},
        {"name": ""},
        {"song_ids": ["one"] * 101},
    ):
        response = client.post("/api/navidrome/playlists", headers=auth(), json=body(**patch))
        assert response.status_code in {400, 422}
    assert not server.created
    assert client.get("/api/navidrome/operations/missing?library_id=2", headers=auth()).status_code == 404
    server.version = "0.65.0"
    assert (
        client.post("/api/navidrome/playlists", headers=auth(), json=body(operation_id="unsupported")).status_code
        == 409
    )
    assert not server.created


def test_readback_mismatch_and_cli_status_report_unresolved(native, monkeypatch, capsys):
    client, app, server, source, embedder, qdrant, settings = native
    server.overrides = {"public": "true"}
    saved = client.post("/api/navidrome/playlists", headers=auth(), json=body())
    assert saved.json()["status"] == "unresolved"
    monkeypatch.setattr(playlists, "Settings", lambda: settings)
    monkeypatch.setattr(playlists, "NavidromeClient", lambda *_: source)
    monkeypatch.setattr(playlists, "prompt_navidrome_credentials", lambda: source.credentials)
    monkeypatch.setattr("sys.argv", ["resonance-playlist", "status", "--operation-id", "operation-1", "--library", "2"])
    with pytest.raises(SystemExit) as exit:
        playlists.main()
    assert exit.value.code == 2
    assert json.loads(capsys.readouterr().out)["reason"] == "readback_mismatch"
    server.overrides = {}
    assert (
        client.get("/api/navidrome/operations/operation-1?library_id=2", headers=auth()).json()["status"] == "verified"
    )
    assert len(server.created) == 1


def test_owned_source_dependency_is_closed_after_request(native, monkeypatch):
    client, app, server, source, embedder, qdrant, settings = native
    del app.state.navidrome
    close = MagicMock()
    source.close = close
    monkeypatch.setattr("resonance.routes.auth.NavidromeClient", lambda *_: source)
    assert client.get("/api/navidrome/connection", headers=auth()).status_code == 200
    close.assert_called_once()


def test_malformed_xml_readback_returns_persisted_unresolved_over_http(native):
    client, app, server, source, embedder, qdrant, settings = native
    server.overrides = {"songCount": "garbage"}
    response = client.post("/api/navidrome/playlists", headers=auth(), json=body())
    assert response.status_code == 200
    assert response.json()["status"] == "unresolved" and response.json()["playlist_id"] == "p-0"
    server.overrides = {}
    assert (
        client.get("/api/navidrome/operations/operation-1?library_id=2", headers=auth()).json()["status"] == "verified"
    )
    assert len(server.created) == 1
