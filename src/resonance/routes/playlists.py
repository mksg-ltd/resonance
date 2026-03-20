"""Playlist endpoint — generate m3u playlists from search results."""

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from resonance.scanner import extract_metadata_from_filename

router = APIRouter(prefix="/api")

# Hardcoded container paths — user mounts host dirs here in docker-compose
MUSIC_DIR = Path("/app/music")
PLAYLISTS_DIR = Path("/app/playlists")


class PlaylistRequest(BaseModel):
    """Playlist creation request."""

    name: str
    tracks: list[str]  # audio_path values (relative to /app/music)


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
def create_playlist(body: PlaylistRequest) -> PlaylistResponse:
    """Create an m3u playlist file from a list of audio paths."""
    if not body.tracks:
        raise HTTPException(status_code=400, detail="tracks list is empty")

    sanitized = _sanitize_name(body.name)
    if not sanitized:
        raise HTTPException(status_code=400, detail="playlist name is empty or contains only special characters")

    PLAYLISTS_DIR.mkdir(parents=True, exist_ok=True)

    filename = f"{sanitized}.m3u"
    m3u_path = PLAYLISTS_DIR / filename

    lines = ["#EXTM3U"]
    for track in body.tracks:
        stem = Path(track).stem
        artist, title = extract_metadata_from_filename(stem)
        display = stem if artist == "Unknown" else f"{artist} - {title}"
        lines.append(f"#EXTINF:0,{display}")
        lines.append(f"../music/{track}")

    m3u_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return PlaylistResponse(name=sanitized, filename=filename, track_count=len(body.tracks))
