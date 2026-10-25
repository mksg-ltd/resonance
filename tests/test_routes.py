"""Tests for API routes."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from fastapi.testclient import TestClient

from resonance.app import create_app
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


class TestSearchRoute:
    @pytest.fixture(autouse=True)
    def _mock_embedder_factory(self):
        """Mock create_embedder_for_name so search tests don't need real conf.d files."""
        mock_embedder = MagicMock()
        mock_embedder.embed.return_value = [[0.1, 0.2, 0.3]]
        mock_embedder.dimensions = 1536
        mock_embedder.model_name = "text-embedding-3-small"
        mock_embedder.provider_name = "openai"
        with patch("resonance.embedders.create_embedder_for_name", return_value=mock_embedder):
            yield

    def test_search_returns_results(self):
        client, mock_qdrant, mock_embedder = _make_test_client()

        # Mock Qdrant search response
        mock_point = MagicMock()
        mock_point.score = 0.95
        mock_point.payload = {
            "artist": "Coldplay",
            "title": "Fix You",
            "album": "X&Y",
            "section": "Chorus",
            "position": 1,
            "total_sections": 4,
            "lyrics": "Lights will guide you home\nAnd ignite your bones",
            "filename": "05 - Coldplay - Fix You.flac",
            "audio_path": "Coldplay/X&Y/05 - Coldplay - Fix You.flac",
            "lyrics_source": "sidecar_lrc",
        }
        mock_qdrant.query_points.return_value = MagicMock(points=[mock_point])

        response = client.post("/api/search", json={"query": "songs about hope", "collection": "test_lyrics"})
        assert response.status_code == 200
        data = response.json()
        assert data["query"] == "songs about hope"
        assert len(data["results"]) == 1
        assert data["results"][0]["artist"] == "Coldplay"
        assert data["results"][0]["score"] == 0.95
        assert data["results"][0]["audio_path"] == "Coldplay/X&Y/05 - Coldplay - Fix You.flac"
        assert data["results"][0]["album"] == "X&Y"

    def test_search_skips_collection_metadata_point(self):
        client, mock_qdrant, _ = _make_test_client()
        metadata = MagicMock(score=0.5, payload={"_metadata": True, "config_name": "test-provider"})
        song = MagicMock(
            score=0.9,
            payload={
                "artist": "Coldplay",
                "title": "Bani Adam",
                "section": "Opening",
                "position": 0,
                "total_sections": 1,
                "lyrics": "sample text",
                "filename": "track.flac",
            },
        )
        mock_qdrant.query_points.return_value = MagicMock(points=[metadata, song])

        response = client.post(
            "/api/search", json={"query": "shared humanity", "collection": "test_lyrics", "limit": 50}
        )

        assert response.status_code == 200
        assert [result["title"] for result in response.json()["results"]] == ["Bani Adam"]

    def test_search_with_artist_filter(self):
        client, mock_qdrant, mock_embedder = _make_test_client()
        mock_qdrant.query_points.return_value = MagicMock(points=[])

        response = client.post("/api/search", json={"query": "love", "collection": "test_lyrics", "artist": "Adele"})
        assert response.status_code == 200

        # Verify filter was passed to Qdrant
        call_kwargs = mock_qdrant.query_points.call_args.kwargs
        assert call_kwargs["query_filter"] is not None

    def test_search_deduplicates_by_song(self):
        client, mock_qdrant, mock_embedder = _make_test_client()

        # Two results from same song, different sections
        point1 = MagicMock()
        point1.score = 0.90
        point1.payload = {
            "artist": "Coldplay",
            "title": "Fix You",
            "album": "X&Y",
            "section": "Verse 1",
            "position": 0,
            "total_sections": 4,
            "lyrics": "When you try your best",
            "filename": "05 - Coldplay - Fix You.flac",
            "audio_path": "Coldplay/X&Y/05 - Coldplay - Fix You.flac",
            "lyrics_source": "sidecar_lrc",
        }
        point2 = MagicMock()
        point2.score = 0.95
        point2.payload = {
            "artist": "Coldplay",
            "title": "Fix You",
            "album": "X&Y",
            "section": "Chorus",
            "position": 1,
            "total_sections": 4,
            "lyrics": "Lights will guide you home",
            "filename": "05 - Coldplay - Fix You.flac",
            "audio_path": "Coldplay/X&Y/05 - Coldplay - Fix You.flac",
            "lyrics_source": "sidecar_lrc",
        }
        mock_qdrant.query_points.return_value = MagicMock(points=[point1, point2])

        response = client.post("/api/search", json={"query": "hope", "collection": "test_lyrics"})
        data = response.json()
        # Should deduplicate — only one result for "Fix You" (highest score)
        assert len(data["results"]) == 1
        assert data["results"][0]["score"] == 0.95
        assert data["results"][0]["section"] == "Chorus"


class TestIngestRoute:
    def _native(self):
        from qdrant_client import QdrantClient
        from tests.test_indexing import FixtureSource, FixtureEmbedder

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
        with patch("resonance.embedders.create_embedder_for_name", return_value=embedder):
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
        with patch("resonance.embedders.create_embedder_for_name", return_value=embedder):
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
