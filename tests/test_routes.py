"""Tests for API routes."""

from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from resonance.app import create_app, dev
from resonance.config import Settings


def _make_test_client(debug: bool = True) -> tuple[TestClient, MagicMock, MagicMock]:
    """Create a test client with mocked Qdrant and embedder."""
    settings = Settings(
        debug=debug,
        qdrant={"url": "http://localhost:6333"},
    )
    app = create_app(settings=settings)

    mock_qdrant = MagicMock()
    mock_qdrant.get_collections.return_value = MagicMock(collections=[])
    # Collection metadata with config_name for search auto-detection
    meta_point = MagicMock()
    meta_point.payload = {
        "_metadata": True,
        "config_name": "test-provider",
        "provider": "openai",
        "model": "text-embedding-3-small",
        "dimensions": 1536,
    }
    mock_qdrant.retrieve.return_value = [meta_point]
    app.state.qdrant = mock_qdrant

    mock_embedder = MagicMock()
    mock_embedder.embed.return_value = [[0.1, 0.2, 0.3]]
    mock_embedder.dimensions = 1536
    mock_embedder.model_name = "text-embedding-3-small"
    mock_embedder.provider_name = "openai"

    return TestClient(app), mock_qdrant, mock_embedder


class TestLocalDevelopmentAccess:
    @pytest.mark.asyncio
    async def test_debug_cors_allows_only_local_static_ui_origins(self):
        app = create_app(settings=Settings(debug=True, _env_file=None))
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            for origin in ("http://localhost:8080", "http://127.0.0.1:8080"):
                response = await client.options(
                    "/api/search",
                    headers={
                        "Origin": origin,
                        "Access-Control-Request-Method": "POST",
                        "Access-Control-Request-Headers": "authorization,content-type",
                    },
                )
                assert response.status_code == 200
                assert response.headers["access-control-allow-origin"] == origin

            blocked = await client.options(
                "/api/search",
                headers={
                    "Origin": "http://example.com",
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "authorization,content-type",
                },
            )
            assert blocked.status_code == 400
            assert "access-control-allow-origin" not in blocked.headers

    def test_debug_runner_binds_to_loopback(self, monkeypatch):
        monkeypatch.setenv("RESONANCE__DEBUG", "false")
        monkeypatch.setenv("RESONANCE__SERVE_DOCS", "false")
        with patch("resonance.app.uvicorn.run") as run:
            dev()

        assert run.call_args.kwargs["host"] == "127.0.0.1"


class TestIngestRoute:
    def _native(self):
        from qdrant_client import QdrantClient

        from tests.test_indexing import FixtureEmbedder, FixtureSource

        source, embedder = FixtureSource(), FixtureEmbedder()
        settings = Settings(api_token="operator-token", navidrome=source.config, _env_file=None)
        app = create_app(settings)
        app.state.qdrant = QdrantClient(":memory:")
        app.state.navidrome = source
        return TestClient(app), app.state.qdrant, source, embedder

    def test_native_ingest_persists_ids_and_skips_unchanged(self):
        client, qdrant, source, embedder = self._native()
        payload = {"provider": "fixture", "library_id": "2", "collection": "native"}
        headers = {"Authorization": "Bearer operator-token"}
        with patch("resonance.embedders.resolve_embedder", return_value=embedder):
            first = client.post("/api/ingest", json=payload, headers=headers)
            assert first.status_code == 200
            assert first.json()["tracks_processed"] == 2
            second = client.post("/api/ingest", json=payload, headers=headers)
            assert second.status_code == 200
            assert second.json()["tracks_unchanged"] == 2
            assert qdrant.get_collection("native").points_count == 5
        qdrant.close()

    def test_native_ingest_mismatch_does_not_append(self):
        client, qdrant, source, embedder = self._native()
        payload = {"provider": "fixture", "library_id": "2", "collection": "native"}
        headers = {"Authorization": "Bearer operator-token"}
        with patch("resonance.embedders.resolve_embedder", return_value=embedder):
            assert client.post("/api/ingest", json=payload, headers=headers).status_code == 200
            count = qdrant.get_collection("native").points_count
            embedder.profile["model"] = "different-model"
            result = client.post("/api/ingest", json=payload, headers=headers)
            assert result.status_code == 409
            assert qdrant.get_collection("native").points_count == count
        qdrant.close()

    def test_native_ingest_is_protected_and_old_path_input_rejected(self):
        client, qdrant, source, embedder = self._native()
        payload = {"provider": "fixture", "library_id": "2"}
        assert client.post("/api/ingest", json=payload).status_code == 401
        result = client.post(
            "/api/ingest", json={**payload, "data_dir": "/music"}, headers={"Authorization": "Bearer operator-token"}
        )
        assert result.status_code == 422
        assert not qdrant.get_collections().collections
        qdrant.close()


class TestConfigRoute:
    def test_get_config(self):
        client, _, _ = _make_test_client()
        response = client.get("/api/config")
        assert response.status_code == 200
        data = response.json()
        assert data["debug"] is True

    def test_config_redacts_secrets(self):
        settings = Settings(
            debug=True,
            qdrant={"url": "http://localhost:6333", "api_key": "secret-key"},
        )
        app = create_app(settings=settings)
        app.state.qdrant = MagicMock()
        client = TestClient(app)

        response = client.get("/api/config")
        data = response.json()
        # SecretStr should be redacted
        assert data["qdrant"]["api_key"] == "**********"


class TestCollectionsRoute:
    def test_list_collections_empty(self):
        client, mock_qdrant, _ = _make_test_client()
        mock_qdrant.get_collections.return_value = MagicMock(collections=[])

        response = client.get("/api/collections")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_collections_with_metadata(self):
        client, mock_qdrant, _ = _make_test_client()

        mock_collection = MagicMock()
        mock_collection.name = "lyrics"
        mock_qdrant.get_collections.return_value = MagicMock(collections=[mock_collection])
        mock_qdrant.get_collection.return_value = MagicMock(points_count=500)

        # Mock metadata point
        meta_point = MagicMock()
        meta_point.payload = {
            "_metadata": True,
            "provider": "openai",
            "model": "text-embedding-3-small",
            "dimensions": 1536,
        }
        mock_qdrant.retrieve.return_value = [meta_point]

        response = client.get("/api/collections")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "lyrics"
        assert data[0]["points_count"] == 500
        assert data[0]["provider"] == "openai"
        assert data[0]["model"] == "text-embedding-3-small"

    def test_delete_collection(self):
        client, mock_qdrant, _ = _make_test_client()

        response = client.delete("/api/collections/test_lyrics")
        assert response.status_code == 200
        assert response.json() == {"deleted": "test_lyrics"}
        mock_qdrant.delete_collection.assert_called_once_with("test_lyrics")
