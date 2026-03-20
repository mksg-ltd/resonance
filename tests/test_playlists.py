"""Tests for playlist generation endpoint."""

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from resonance.app import create_app
from resonance.config import Settings


def _make_client() -> TestClient:
    """Create a test client."""
    settings = Settings(debug=True, qdrant={"url": "http://localhost:6333"})
    app = create_app(settings=settings)
    app.state.qdrant = MagicMock()
    return TestClient(app)


class TestCreatePlaylist:
    def test_creates_m3u_file(self, tmp_path):
        client = _make_client()

        response = client.post("/api/playlists", json={
            "name": "My Playlist",
            "data_dir": str(tmp_path),
            "tracks": [
                "Coldplay/Ghost Stories/03 - Coldplay - Ghost Story.flac",
                "Passenger/All The Little Lights/03 - Passenger - Let Her Go.flac",
            ],
        })

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "my-playlist"
        assert data["filename"] == "my-playlist.m3u"
        assert data["track_count"] == 2

        m3u_path = tmp_path / "playlists" / "my-playlist.m3u"
        assert m3u_path.exists()
        content = m3u_path.read_text()
        assert content.startswith("#EXTM3U\n")
        assert "../Coldplay/Ghost Stories/03 - Coldplay - Ghost Story.flac" in content
        assert "../Passenger/All The Little Lights/03 - Passenger - Let Her Go.flac" in content

    def test_creates_playlists_dir_if_missing(self, tmp_path):
        client = _make_client()

        response = client.post("/api/playlists", json={
            "name": "test",
            "data_dir": str(tmp_path),
            "tracks": ["some/path.flac"],
        })

        assert response.status_code == 200
        assert (tmp_path / "playlists").exists()

    def test_overwrites_existing_playlist(self, tmp_path):
        client = _make_client()

        payload = {"data_dir": str(tmp_path)}
        client.post("/api/playlists", json={**payload, "name": "test", "tracks": ["a.flac"]})
        client.post("/api/playlists", json={**payload, "name": "test", "tracks": ["b.flac", "c.flac"]})

        content = (tmp_path / "playlists" / "test.m3u").read_text()
        assert "../b.flac" in content
        assert "../c.flac" in content
        assert "../a.flac" not in content

    def test_400_empty_tracks(self, tmp_path):
        client = _make_client()
        response = client.post("/api/playlists", json={"name": "test", "data_dir": str(tmp_path), "tracks": []})
        assert response.status_code == 400

    def test_400_empty_name(self, tmp_path):
        client = _make_client()
        response = client.post("/api/playlists", json={"name": "", "data_dir": str(tmp_path), "tracks": ["a.flac"]})
        assert response.status_code == 400

    def test_400_name_sanitizes_to_empty(self, tmp_path):
        client = _make_client()
        response = client.post("/api/playlists", json={"name": "!!!", "data_dir": str(tmp_path), "tracks": ["a.flac"]})
        assert response.status_code == 400

    def test_500_readonly_volume(self, tmp_path):
        """Should return 500 with helpful message when volume is read-only."""
        client = _make_client()
        response = client.post("/api/playlists", json={
            "name": "test",
            "data_dir": "/nonexistent/readonly/path",
            "tracks": ["a.flac"],
        })
        assert response.status_code == 500
        assert "read-only" in response.json()["detail"] or "Cannot create" in response.json()["detail"]

    def test_extinf_extracts_artist_title(self, tmp_path):
        client = _make_client()

        client.post("/api/playlists", json={
            "name": "test",
            "data_dir": str(tmp_path),
            "tracks": ["Artist/Album/03 - Coldplay - Fix You.flac"],
        })

        content = (tmp_path / "playlists" / "test.m3u").read_text()
        assert "#EXTINF:0,Coldplay - Fix You" in content

    def test_extinf_precedes_track_path(self, tmp_path):
        """Each #EXTINF line must immediately precede its track path."""
        client = _make_client()

        client.post("/api/playlists", json={
            "name": "test",
            "data_dir": str(tmp_path),
            "tracks": [
                "A/01 - Artist1 - Song1.flac",
                "B/02 - Artist2 - Song2.flac",
            ],
        })

        content = (tmp_path / "playlists" / "test.m3u").read_text()
        assert "#EXTINF:0,Artist1 - Song1\n../A/01 - Artist1 - Song1.flac" in content
        assert "#EXTINF:0,Artist2 - Song2\n../B/02 - Artist2 - Song2.flac" in content

    def test_extinf_fallback_for_unparseable_filename(self, tmp_path):
        """Filenames without artist-title pattern use the stem as display name."""
        client = _make_client()

        client.post("/api/playlists", json={
            "name": "test",
            "data_dir": str(tmp_path),
            "tracks": ["some/dir/mysong.flac"],
        })

        content = (tmp_path / "playlists" / "test.m3u").read_text()
        assert "#EXTINF:0,mysong" in content


class TestNameSanitization:
    def test_spaces_to_hyphens(self, tmp_path):
        client = _make_client()
        response = client.post("/api/playlists", json={"name": "My Cool Playlist", "data_dir": str(tmp_path), "tracks": ["a.flac"]})
        assert response.json()["name"] == "my-cool-playlist"

    def test_special_chars_removed(self, tmp_path):
        client = _make_client()
        response = client.post("/api/playlists", json={"name": "Rock & Roll!!", "data_dir": str(tmp_path), "tracks": ["a.flac"]})
        assert response.json()["name"] == "rock-roll"

    def test_collapses_multiple_hyphens(self, tmp_path):
        client = _make_client()
        response = client.post("/api/playlists", json={"name": "a - - b", "data_dir": str(tmp_path), "tracks": ["a.flac"]})
        assert response.json()["name"] == "a-b"
