# m3u Playlist Generation

**Date:** 2026-03-20
**Status:** Draft
**Depends on:** Library Scanner spec (2026-03-20-library-scanner-design.md) — implemented

---

## Context

resonance can search for songs by mood/meaning and returns results with `audio_path` (relative path to the audio file on disk). There is no way to turn search results into something a music player can consume.

Both Jellyfin and Navidrome auto-discover m3u files during library scans and resolve relative paths relative to the m3u file's location. This makes m3u the universal, server-agnostic playlist format for self-hosted setups.

## Goals

- New API endpoint to create m3u playlists from a list of audio paths
- Playlists written to a configurable directory on disk
- m3u files use relative paths so they work across Docker containers with different mount points

## Non-Goals

- UI changes (checkbox selection, "Create Playlist" button) — separate work
- Subsonic API integration
- Playlist management (list, delete, update) — can be added later
- Track duration in `#EXTINF` — we don't store it, players handle `0` gracefully

## Design

### API Endpoint

```
POST /api/playlists
```

Request body:

```python
class PlaylistRequest(BaseModel):
    name: str                    # playlist name, will be sanitized for filename
    tracks: list[str]            # audio_path values from Qdrant search results
```

Response body:

```python
class PlaylistResponse(BaseModel):
    name: str                    # sanitized playlist name
    filename: str                # e.g. "letting-go-mix.m3u"
    track_count: int
    path: str                    # relative path from playlists_dir, e.g. "letting-go-mix.m3u"
```

Behavior:

1. Sanitize `name` for use as a filename (strip special chars, replace spaces with hyphens, lowercase)
2. Create `playlists_dir` if it doesn't exist
3. Write m3u file to `{playlists_dir}/{sanitized_name}.m3u`
4. If a file with the same name exists, overwrite it
5. Return playlist metadata

Errors:

- `400` if `tracks` is empty
- `400` if `name` is empty or sanitizes to empty
- `500` if `playlists_dir` is not configured

### m3u File Format

```
#EXTM3U
#EXTINF:0,Passenger - Let Her Go
../Passenger/All The Little Lights/03 - Passenger - Let Her Go.flac
#EXTINF:0,Coldplay - Ghost Story
../Coldplay/Ghost Stories/03 - Coldplay - Ghost Story.flac
```

- `#EXTM3U` header — identifies extended m3u format
- `#EXTINF:0,{Artist} - {Title}` — duration is `0` (unknown), display name from the audio path
- `../{audio_path}` — relative path from the `Playlists/` directory up one level to `data_dir`, then down to the audio file

The `..` prefix is because `playlists_dir` is expected to be one level inside the music root (e.g., `/data/media/music/english/Playlists/`). Since `audio_path` in Qdrant is relative to that music root, `../{audio_path}` resolves correctly.

**Artist and title for `#EXTINF`:** Extract from the `audio_path` filename stem using the existing `_extract_metadata_from_filename` logic in `scanner.py`. This avoids a Qdrant lookup — the audio_path alone contains enough information. If parsing fails, use the full filename as the display name.

### Configuration

Add to `config.py`:

```python
class PlaylistConfig(BaseModel):
    """Playlist generation settings."""

    dir: str | None = None  # absolute path to playlists directory
```

Add to `Settings`:

```python
playlists: PlaylistConfig = PlaylistConfig()
```

Example `config.yml`:

```yaml
playlists:
  dir: /data/media/music/english/Playlists
```

If `playlists.dir` is not set, the endpoint returns a `500` with a clear error message.

### File Layout

```
src/resonance/
├── routes/
│   └── playlists.py    # NEW — POST /api/playlists endpoint
├── config.py           # MODIFY — add PlaylistConfig
├── app.py              # MODIFY — register playlists router
└── scanner.py          # reuse _extract_metadata_from_filename (already public-ish)
```

The m3u writing logic lives directly in `routes/playlists.py` — it's ~20 lines, no need for a separate module.

### Name Sanitization

Playlist name → filename conversion:

1. Strip leading/trailing whitespace
2. Replace spaces with hyphens
3. Remove characters not in `[a-zA-Z0-9_-]`
4. Lowercase
5. Collapse multiple hyphens into one
6. If result is empty after sanitization, return `400`

Example: `"Songs About Letting Go!"` → `"songs-about-letting-go"`

### Exposing \_extract_metadata_from_filename

The function `_extract_metadata_from_filename` in `scanner.py` is currently module-private (prefixed with `_`). Since the playlist endpoint needs it to generate `#EXTINF` display names, rename it to `extract_metadata_from_filename` (drop the underscore) and keep it in `scanner.py`. It has no dependencies beyond `re` and is a pure function.
