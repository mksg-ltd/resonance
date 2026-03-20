# m3u Playlist Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `POST /api/playlists` endpoint that takes a list of audio paths and writes an m3u playlist file to a configurable directory.

**Architecture:** New route module `routes/playlists.py` with inline m3u writing logic. Config gains a `PlaylistConfig` with a `dir` field. The existing `_extract_metadata_from_filename` in scanner.py is renamed public for reuse.

**Tech Stack:** Python 3.14, FastAPI, pytest

**Spec:** `docs/superpowers/specs/2026-03-20-m3u-playlist-design.md`

---

### Task 1: Add PlaylistConfig and rename scanner helper

**Files:**

- Modify: `src/resonance/config.py:25-37` (add PlaylistConfig, add to Settings)
- Modify: `src/resonance/scanner.py:171,183` (rename `_extract_metadata_from_filename` → `extract_metadata_from_filename`)
- Modify: `tests/test_config.py` (add playlist config test)

- [ ] **Step 1: Write test for playlist config defaults**

Add to `tests/test_config.py`:

```python
def test_playlist_defaults_to_none():
    settings = Settings(
        server={"debug": True},
        qdrant={"url": "http://localhost:6333"},
    )
    assert settings.playlists.dir is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_config.py::test_playlist_defaults_to_none -v`
Expected: FAIL — `playlists` not in Settings

- [ ] **Step 3: Add PlaylistConfig to config.py**

Add after `ChunkingConfig` (around line 30):

```python
class PlaylistConfig(BaseModel):
    """Playlist generation settings."""

    dir: str | None = None
```

Add to `Settings` class (after `jellyfin` line):

```python
playlists: PlaylistConfig = PlaylistConfig()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 5: Rename \_extract_metadata_from_filename in scanner.py**

In `src/resonance/scanner.py`:

- Line 183: rename `def _extract_metadata_from_filename` → `def extract_metadata_from_filename`
- Line 171: update the call site in `_read_metadata` to use `extract_metadata_from_filename`

- [ ] **Step 6: Run all tests to verify nothing breaks**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: ALL PASS (67+ tests)

- [ ] **Step 7: Commit**

```bash
git add src/resonance/config.py src/resonance/scanner.py tests/test_config.py
git commit -m "feat: add PlaylistConfig, make extract_metadata_from_filename public"
```

---

### Task 2: Create playlists route with tests

**Files:**

- Create: `src/resonance/routes/playlists.py`
- Create: `tests/test_playlists.py`
- Modify: `src/resonance/app.py:20,78` (import and register router)

- [ ] **Step 1: Write tests**

Create `tests/test_playlists.py`:

```python
"""Tests for playlist generation endpoint."""

import re
from pathlib import Path
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from resonance.app import create_app
from resonance.config import Settings


def _make_client(playlists_dir: str | None = None) -> TestClient:
    """Create a test client with optional playlists config."""
    settings_kwargs = {
        "server": {"debug": True},
        "qdrant": {"url": "http://localhost:6333"},
    }
    if playlists_dir:
        settings_kwargs["playlists"] = {"dir": playlists_dir}

    settings = Settings(**settings_kwargs)
    app = create_app(settings=settings)
    app.state.qdrant = MagicMock()
    app.state.embedder = MagicMock()
    return TestClient(app)


class TestCreatePlaylist:
    def test_creates_m3u_file(self, tmp_path):
        client = _make_client(playlists_dir=str(tmp_path))

        response = client.post("/api/playlists", json={
            "name": "My Playlist",
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

        # Verify m3u file was written
        m3u_path = tmp_path / "my-playlist.m3u"
        assert m3u_path.exists()
        content = m3u_path.read_text()
        assert content.startswith("#EXTM3U\n")
        assert "../Coldplay/Ghost Stories/03 - Coldplay - Ghost Story.flac" in content
        assert "../Passenger/All The Little Lights/03 - Passenger - Let Her Go.flac" in content
        assert "#EXTINF:0," in content

    def test_creates_playlists_dir_if_missing(self, tmp_path):
        playlists_dir = tmp_path / "Playlists"
        client = _make_client(playlists_dir=str(playlists_dir))

        response = client.post("/api/playlists", json={
            "name": "test",
            "tracks": ["some/path.flac"],
        })

        assert response.status_code == 200
        assert playlists_dir.exists()

    def test_overwrites_existing_playlist(self, tmp_path):
        client = _make_client(playlists_dir=str(tmp_path))

        # Create first
        client.post("/api/playlists", json={"name": "test", "tracks": ["a.flac"]})
        # Overwrite
        client.post("/api/playlists", json={"name": "test", "tracks": ["b.flac", "c.flac"]})

        content = (tmp_path / "test.m3u").read_text()
        assert "../b.flac" in content
        assert "../c.flac" in content
        assert "../a.flac" not in content

    def test_400_empty_tracks(self, tmp_path):
        client = _make_client(playlists_dir=str(tmp_path))

        response = client.post("/api/playlists", json={"name": "test", "tracks": []})
        assert response.status_code == 400

    def test_400_empty_name(self, tmp_path):
        client = _make_client(playlists_dir=str(tmp_path))

        response = client.post("/api/playlists", json={"name": "", "tracks": ["a.flac"]})
        assert response.status_code == 400

    def test_400_name_sanitizes_to_empty(self, tmp_path):
        client = _make_client(playlists_dir=str(tmp_path))

        response = client.post("/api/playlists", json={"name": "!!!", "tracks": ["a.flac"]})
        assert response.status_code == 400

    def test_503_playlists_dir_not_configured(self):
        client = _make_client(playlists_dir=None)

        response = client.post("/api/playlists", json={"name": "test", "tracks": ["a.flac"]})
        assert response.status_code == 503
        assert "not configured" in response.json()["detail"]

    def test_extinf_extracts_artist_title(self, tmp_path):
        client = _make_client(playlists_dir=str(tmp_path))

        client.post("/api/playlists", json={
            "name": "test",
            "tracks": ["Artist/Album/03 - Coldplay - Fix You.flac"],
        })

        content = (tmp_path / "test.m3u").read_text()
        assert "#EXTINF:0,Coldplay - Fix You" in content

    def test_extinf_precedes_track_path(self, tmp_path):
        """Each #EXTINF line must immediately precede its track path."""
        client = _make_client(playlists_dir=str(tmp_path))

        client.post("/api/playlists", json={
            "name": "test",
            "tracks": [
                "A/01 - Artist1 - Song1.flac",
                "B/02 - Artist2 - Song2.flac",
            ],
        })

        content = (tmp_path / "test.m3u").read_text()
        assert "#EXTINF:0,Artist1 - Song1\n../A/01 - Artist1 - Song1.flac" in content
        assert "#EXTINF:0,Artist2 - Song2\n../B/02 - Artist2 - Song2.flac" in content

    def test_extinf_fallback_for_unparseable_filename(self, tmp_path):
        """Filenames without artist-title pattern use the stem as display name."""
        client = _make_client(playlists_dir=str(tmp_path))

        client.post("/api/playlists", json={
            "name": "test",
            "tracks": ["some/dir/mysong.flac"],
        })

        content = (tmp_path / "test.m3u").read_text()
        assert "#EXTINF:0,mysong" in content


class TestNameSanitization:
    def test_spaces_to_hyphens(self, tmp_path):
        client = _make_client(playlists_dir=str(tmp_path))
        response = client.post("/api/playlists", json={"name": "My Cool Playlist", "tracks": ["a.flac"]})
        assert response.json()["name"] == "my-cool-playlist"

    def test_special_chars_removed(self, tmp_path):
        client = _make_client(playlists_dir=str(tmp_path))
        response = client.post("/api/playlists", json={"name": "Rock & Roll!!", "tracks": ["a.flac"]})
        assert response.json()["name"] == "rock-roll"

    def test_collapses_multiple_hyphens(self, tmp_path):
        client = _make_client(playlists_dir=str(tmp_path))
        response = client.post("/api/playlists", json={"name": "a - - b", "tracks": ["a.flac"]})
        assert response.json()["name"] == "a-b"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_playlists.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Create routes/playlists.py**

Create `src/resonance/routes/playlists.py`:

```python
"""Playlist endpoint — generate m3u playlists from search results."""

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from resonance.scanner import extract_metadata_from_filename

router = APIRouter(prefix="/api")


class PlaylistRequest(BaseModel):
    """Playlist creation request."""

    name: str
    tracks: list[str]


class PlaylistResponse(BaseModel):
    """Playlist creation response."""

    name: str
    filename: str
    track_count: int


def _sanitize_name(name: str) -> str:
    """Convert playlist name to a safe filename."""
    result = name.strip().lower()
    result = result.replace(" ", "-")
    result = re.sub(r"[^a-z0-9_-]", "", result)
    result = re.sub(r"-{2,}", "-", result)
    return result.strip("-")


@router.post("/playlists", response_model=PlaylistResponse)
def create_playlist(body: PlaylistRequest, request: Request) -> PlaylistResponse:
    """Create an m3u playlist file from a list of audio paths."""
    settings = request.app.state.settings

    if not settings.playlists.dir:
        raise HTTPException(status_code=503, detail="playlists.dir is not configured")

    if not body.tracks:
        raise HTTPException(status_code=400, detail="tracks list is empty")

    sanitized = _sanitize_name(body.name)
    if not sanitized:
        raise HTTPException(status_code=400, detail="playlist name is empty or contains only special characters")

    # Write m3u file
    playlists_dir = Path(settings.playlists.dir)
    playlists_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{sanitized}.m3u"
    m3u_path = playlists_dir / filename

    lines = ["#EXTM3U"]
    for track in body.tracks:
        stem = Path(track).stem
        artist, title = extract_metadata_from_filename(stem)
        display = stem if artist == "Unknown" else f"{artist} - {title}"
        lines.append(f"#EXTINF:0,{display}")
        lines.append(f"../{track}")

    m3u_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return PlaylistResponse(name=sanitized, filename=filename, track_count=len(body.tracks))
```

- [ ] **Step 4: Register router in app.py**

In `src/resonance/app.py`, add import:

```python
from resonance.routes.playlists import router as playlists_router
```

Add after the collections router registration:

```python
app.include_router(playlists_router)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_playlists.py -v`
Expected: ALL PASS

- [ ] **Step 6: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 7: Run linter**

Run: `.venv/bin/python -m ruff check src/resonance/routes/playlists.py --fix`
Expected: clean

- [ ] **Step 8: Commit**

```bash
git add src/resonance/routes/playlists.py src/resonance/app.py tests/test_playlists.py
git commit -m "feat: add POST /api/playlists endpoint for m3u generation"
```

---

## Summary of Changes

| File                                | Action | Description                                                                 |
| ----------------------------------- | ------ | --------------------------------------------------------------------------- |
| `src/resonance/config.py`           | Modify | Add `PlaylistConfig` and `playlists` field to Settings                      |
| `src/resonance/scanner.py`          | Modify | Rename `_extract_metadata_from_filename` → `extract_metadata_from_filename` |
| `src/resonance/routes/playlists.py` | Create | `POST /api/playlists` — sanitize name, write m3u, return metadata           |
| `src/resonance/app.py`              | Modify | Register playlists router                                                   |
| `tests/test_config.py`              | Modify | Add playlist config defaults test                                           |
| `tests/test_playlists.py`           | Create | 11 tests covering creation, errors, sanitization, EXTINF                    |
