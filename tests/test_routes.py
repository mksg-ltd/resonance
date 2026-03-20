"""Tests for API routes."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from resonance.app import create_app
from resonance.config import Settings


def _make_test_client(debug: bool = True) -> tuple[TestClient, MagicMock, MagicMock]:
    """Create a test client with mocked Qdrant and embedder."""
    settings = Settings(
        server={"debug": debug},
        qdrant={"url": "http://localhost:6333", "collection": "test_lyrics"},
    )
    app = create_app(settings=settings)

    mock_qdrant = MagicMock()
    mock_qdrant.get_collections.return_value = MagicMock(collections=[])
    mock_qdrant.retrieve.return_value = []  # No metadata point — use default embedder
    app.state.qdrant = mock_qdrant

    mock_embedder = MagicMock()
    mock_embedder.embed.return_value = [[0.1, 0.2, 0.3]]
    mock_embedder.dimensions = 1536
    mock_embedder.model_name = "text-embedding-3-small"
    mock_embedder.provider_name = "openai"
    app.state.embedder = mock_embedder

    return TestClient(app), mock_qdrant, mock_embedder


class TestSearchRoute:
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

        response = client.post("/api/search", json={"query": "songs about hope"})
        assert response.status_code == 200
        data = response.json()
        assert data["query"] == "songs about hope"
        assert len(data["results"]) == 1
        assert data["results"][0]["artist"] == "Coldplay"
        assert data["results"][0]["score"] == 0.95
        assert data["results"][0]["audio_path"] == "Coldplay/X&Y/05 - Coldplay - Fix You.flac"
        assert data["results"][0]["album"] == "X&Y"

    def test_search_with_artist_filter(self):
        client, mock_qdrant, mock_embedder = _make_test_client()
        mock_qdrant.query_points.return_value = MagicMock(points=[])

        response = client.post("/api/search", json={"query": "love", "artist": "Adele"})
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

        response = client.post("/api/search", json={"query": "hope"})
        data = response.json()
        # Should deduplicate — only one result for "Fix You" (highest score)
        assert len(data["results"]) == 1
        assert data["results"][0]["score"] == 0.95
        assert data["results"][0]["section"] == "Chorus"


class TestIngestRoute:
    def test_ingest_incremental_skips_existing(self, tmp_path):
        """Incremental ingest skips songs already in the collection."""
        _, mock_qdrant, mock_embedder = _make_test_client()

        # Collection exists with one song already ingested
        mock_collection = MagicMock()
        mock_collection.name = "test_lyrics"
        mock_qdrant.get_collections.return_value = MagicMock(collections=[mock_collection])
        mock_qdrant.get_collection.return_value = MagicMock(points_count=5)

        # Model matches
        meta_point = MagicMock()
        meta_point.payload = {"_metadata": True, "model": "text-embedding-3-small"}
        mock_qdrant.retrieve.return_value = [meta_point]

        # Existing audio_path in collection
        existing_point = MagicMock()
        existing_point.payload = {"audio_path": "01 - Test Artist - Test Song.flac"}
        mock_qdrant.scroll.return_value = ([existing_point], None)

        # Create the same file on disk — should be skipped
        audio_file = tmp_path / "01 - Test Artist - Test Song.flac"
        audio_file.write_bytes(b"\x00" * 64)
        lrc_file = tmp_path / "01 - Test Artist - Test Song.lrc"
        lrc_file.write_text("[00:00.00] Test line\n[00:05.00] Another line\n")

        from resonance.routes.ingest import run_ingest

        result = run_ingest(
            qdrant=mock_qdrant,
            embedder=mock_embedder,
            settings=Settings(
                server={"debug": True},
                qdrant={"url": "http://localhost:6333", "collection": "test_lyrics"},
            ),
            collection="test_lyrics",
            force=False,
            data_dir=tmp_path,
        )

        assert result.files_processed == 0
        assert result.chunks_created == 0

    def test_ingest_warns_on_model_mismatch(self):
        _, mock_qdrant, mock_embedder = _make_test_client()

        mock_collection = MagicMock()
        mock_collection.name = "test_lyrics"
        mock_qdrant.get_collections.return_value = MagicMock(collections=[mock_collection])
        mock_qdrant.get_collection.return_value = MagicMock(points_count=100)

        # Stored model differs from active embedder
        meta_point = MagicMock()
        meta_point.payload = {"_metadata": True, "model": "text-embedding-3-large"}
        mock_qdrant.retrieve.return_value = [meta_point]

        from resonance.routes.ingest import run_ingest

        result = run_ingest(
            qdrant=mock_qdrant,
            embedder=mock_embedder,
            settings=Settings(
                server={"debug": True},
                qdrant={"url": "http://localhost:6333", "collection": "test_lyrics"},
            ),
            collection="test_lyrics",
            force=False,
            data_dir=Path("/dummy"),
        )

        assert result.model_mismatch is True
        assert result.stored_model == "text-embedding-3-large"

    def test_ingest_processes_audio_files(self, tmp_path):
        """Test that audio files with sidecar LRC are ingested via LibraryScanner."""
        _, mock_qdrant, mock_embedder = _make_test_client()
        mock_qdrant.get_collections.return_value = MagicMock(collections=[])

        lrc_content = "[00:00.00] Test line one\n[00:05.00] Test line two\n[00:10.00] Test line three\n[00:15.00] Test line four\n"
        audio_file = tmp_path / "01 - Test Artist - Test Song.flac"
        audio_file.write_bytes(b"\x00" * 64)
        lrc_file = tmp_path / "01 - Test Artist - Test Song.lrc"
        lrc_file.write_text(lrc_content)

        mock_embedder.embed.return_value = [[0.1] * 1536]

        from resonance.routes.ingest import run_ingest

        result = run_ingest(
            qdrant=mock_qdrant,
            embedder=mock_embedder,
            settings=Settings(
                server={"debug": True},
                qdrant={"url": "http://localhost:6333", "collection": "test_lyrics"},
            ),
            collection="test_lyrics",
            force=True,
            data_dir=tmp_path,
        )

        assert result.files_processed == 1
        assert result.chunks_created >= 1

        # Verify new payload fields in upserted points
        upsert_call = mock_qdrant.upsert.call_args_list[-1]
        points = upsert_call.kwargs["points"]
        payload = points[0].payload
        assert "audio_path" in payload
        assert "lyrics_source" in payload
        assert payload["filename"].endswith(".flac")


class TestConfigRoute:
    def test_get_config(self):
        client, _, _ = _make_test_client()
        response = client.get("/api/config")
        assert response.status_code == 200
        data = response.json()
        assert data["embedding"]["provider"] == "openai"
        assert data["qdrant"]["collection"] == "test_lyrics"
        assert data["server"]["debug"] is True

    def test_config_redacts_secrets(self):
        settings = Settings(
            server={"debug": True},
            qdrant={"url": "http://localhost:6333", "api_key": "secret-key"},
        )
        app = create_app(settings=settings)
        app.state.qdrant = MagicMock()
        app.state.embedder = MagicMock()
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
        meta_point.payload = {"_metadata": True, "provider": "openai", "model": "text-embedding-3-small", "dimensions": 1536}
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
