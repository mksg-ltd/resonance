# Library Scanner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the LRC-file-first ingest pipeline with an audio-file-first library scanner that extracts lyrics from embedded tags (mutagen) or sidecar LRC files, stores richer metadata in Qdrant, and enables future m3u playlist generation.

**Architecture:** A new `LibraryScanner` scans for audio files, tries embedded synced lyrics first (via mutagen), falls back to sidecar `.lrc` files, and yields `SongData` objects. The ingest pipeline consumes `SongData` instead of raw file paths. Qdrant payloads gain `audio_path`, `album`, and `lyrics_source` fields.

**Tech Stack:** Python 3.14, mutagen (audio tags), FastAPI, Qdrant, pytest

**Spec:** `docs/superpowers/specs/2026-03-20-library-scanner-design.md`

---

### Task 1: Add mutagen dependency

**Files:**

- Modify: `pyproject.toml:7-15` (add mutagen to dependencies)

- [ ] **Step 1: Add mutagen to project dependencies**

In `pyproject.toml`, add `"mutagen>=1.47.0"` to the `dependencies` list.

- [ ] **Step 2: Install**

Run: `uv sync`
Expected: mutagen installed, lock file updated

- [ ] **Step 3: Verify import works**

Run: `uv run python -c "import mutagen; print(mutagen.version_string)"`
Expected: prints mutagen version

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add mutagen dependency for audio tag reading"
```

---

### Task 2: Add `SongData` model and `parse_lrc_text`

**Files:**

- Modify: `src/resonance/models.py` (add `SongData` dataclass)
- Modify: `src/resonance/parser.py` (add `parse_lrc_text` function)
- Create: `tests/test_models.py`
- Modify: `tests/test_routes.py` (will need updates later, not in this task)

- [ ] **Step 1: Write tests for SongData**

Create `tests/test_models.py`:

```python
"""Tests for domain models."""

from pathlib import Path

from resonance.models import LrcLine, SongData


class TestSongData:
    def test_creation_with_required_fields(self):
        lines = [LrcLine(timestamp_sec=0.0, text="hello"), LrcLine(timestamp_sec=5.0, text="world")]
        song = SongData(
            artist="Coldplay",
            title="Fix You",
            audio_path=Path("/music/Coldplay/Fix You.flac"),
            filename="Fix You.flac",
            lines=lines,
        )
        assert song.artist == "Coldplay"
        assert song.title == "Fix You"
        assert song.album is None
        assert song.lyrics_source == "sidecar_lrc"

    def test_creation_with_all_fields(self):
        lines = [LrcLine(timestamp_sec=0.0, text="hello")]
        song = SongData(
            artist="Coldplay",
            title="Fix You",
            audio_path=Path("/music/Coldplay/Fix You.flac"),
            filename="Fix You.flac",
            lines=lines,
            album="X&Y",
            lyrics_source="embedded",
        )
        assert song.album == "X&Y"
        assert song.lyrics_source == "embedded"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_models.py -v`
Expected: FAIL — `SongData` not defined

- [ ] **Step 3: Add SongData to models.py**

Add to `src/resonance/models.py` after the `LrcChunk` class (before `LrcLyric`):

```python
@dataclass
class SongData:
    """A discovered song with its lyrics and metadata.

    Yielded by LibraryScanner, consumed by the ingest pipeline.
    """

    artist: str
    title: str
    audio_path: Path
    filename: str
    lines: list[LrcLine]
    album: str | None = None
    lyrics_source: str = "sidecar_lrc"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_models.py -v`
Expected: PASS

- [ ] **Step 5: Write test for parse_lrc_text**

Add to `tests/test_models.py`:

```python
from resonance.parser import parse_lrc_text


class TestParseLrcText:
    def test_parses_timestamped_lines(self):
        text = "[00:00.00] First line\n[00:05.50] Second line\n[00:10.00] Third line"
        lines = parse_lrc_text(text)
        assert len(lines) == 3
        assert lines[0].text == "First line"
        assert lines[0].timestamp_sec == 0.0
        assert lines[1].timestamp_sec == 5.5

    def test_skips_non_timestamped_lines(self):
        text = "[ti:Song Title]\n[00:00.00] Actual lyrics\nno timestamp here"
        lines = parse_lrc_text(text)
        assert len(lines) == 1
        assert lines[0].text == "Actual lyrics"

    def test_empty_string_returns_empty_list(self):
        assert parse_lrc_text("") == []

    def test_three_digit_fractional_seconds(self):
        text = "[01:23.456] Line with ms precision"
        lines = parse_lrc_text(text)
        assert len(lines) == 1
        assert abs(lines[0].timestamp_sec - 83.456) < 0.001
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `uv run pytest tests/test_models.py::TestParseLrcText -v`
Expected: FAIL — `parse_lrc_text` not defined

- [ ] **Step 7: Implement parse_lrc_text**

Add to `src/resonance/parser.py`:

```python
def parse_lrc_text(text: str) -> list[LrcLine]:
    """Parse LRC-formatted text from memory into timestamped lines.

    Same logic as parse_lrc_lines but accepts a string instead of a file path.
    Used by the scanner for embedded lyrics that are in LRC format.
    """
    lines = []
    for raw_line in text.splitlines():
        m = TIMESTAMP_RE.match(raw_line.strip())
        if not m:
            continue
        mins, secs, frac = int(m.group(1)), int(m.group(2)), m.group(3)
        frac_sec = int(frac) / 100 if len(frac) == 2 else int(frac) / 1000
        timestamp = mins * 60 + secs + frac_sec
        text_content = m.group(4).strip()
        lines.append(LrcLine(timestamp_sec=timestamp, text=text_content))
    return lines
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `uv run pytest tests/test_models.py -v`
Expected: ALL PASS

- [ ] **Step 9: Commit**

```bash
git add src/resonance/models.py src/resonance/parser.py tests/test_models.py
git commit -m "feat: add SongData model and parse_lrc_text for in-memory LRC parsing"
```

---

### Task 3: Update chunker to accept SongData

**Files:**

- Modify: `src/resonance/chunker.py` (add `chunk_song_data`, keep `chunk_song` temporarily)
- Create: `tests/test_chunker.py`

- [ ] **Step 1: Write tests for chunk_song_data**

Create `tests/test_chunker.py`:

```python
"""Tests for chunking logic."""

from pathlib import Path

from resonance.chunker import chunk_song_data
from resonance.models import LrcLine, SongData


def _make_song(lines: list[LrcLine], artist: str = "Test", title: str = "Song") -> SongData:
    return SongData(
        artist=artist,
        title=title,
        audio_path=Path("/music/test.flac"),
        filename="test.flac",
        lines=lines,
    )


class TestChunkSongData:
    def test_chunks_by_time_gaps(self):
        lines = [
            LrcLine(0.0, "Line one"),
            LrcLine(2.0, "Line two"),
            LrcLine(3.0, "Line three"),
            # big gap
            LrcLine(15.0, "Line four"),
            LrcLine(17.0, "Line five"),
        ]
        song = _make_song(lines)
        chunks = chunk_song_data(song, gap_threshold_sec=5.0)
        assert len(chunks) == 2
        assert chunks[0].position == 0
        assert chunks[0].total_chunks == 2
        assert chunks[1].position == 1

    def test_chunks_by_section_tags(self):
        lines = [
            LrcLine(0.0, "[Verse 1] First verse line"),
            LrcLine(5.0, "Second verse line"),
            LrcLine(10.0, "[Chorus] Chorus line"),
            LrcLine(15.0, "More chorus"),
        ]
        song = _make_song(lines)
        chunks = chunk_song_data(song, gap_threshold_sec=5.0)
        assert len(chunks) == 2
        assert chunks[0].section_name == "Verse 1"
        assert chunks[1].section_name == "Chorus"

    def test_returns_empty_for_no_lines(self):
        song = _make_song([])
        chunks = chunk_song_data(song, gap_threshold_sec=5.0)
        assert chunks == []

    def test_min_chunk_lines_merges_tiny_chunks(self):
        lines = [
            LrcLine(0.0, "A"),
            # big gap
            LrcLine(10.0, "B"),
            # big gap
            LrcLine(20.0, "C"),
            LrcLine(22.0, "D"),
            LrcLine(24.0, "E"),
        ]
        song = _make_song(lines)
        # "B" alone is only 1 line, below min_chunk_lines=2, so it merges into "A"
        chunks = chunk_song_data(song, gap_threshold_sec=5.0, min_chunk_lines=2)
        assert len(chunks) == 2

    def test_filters_empty_chunks(self):
        lines = [
            LrcLine(0.0, ""),
            LrcLine(1.0, ""),
            LrcLine(10.0, "Actual content"),
            LrcLine(12.0, "More content"),
        ]
        song = _make_song(lines)
        chunks = chunk_song_data(song, gap_threshold_sec=5.0)
        # The empty-only chunk should be filtered out
        for chunk in chunks:
            assert chunk.lyrics.strip() != ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_chunker.py -v`
Expected: FAIL — `chunk_song_data` not found

- [ ] **Step 3: Implement chunk_song_data**

Add to `src/resonance/chunker.py`, after the existing `chunk_song` function:

```python
from .models import SongData


def chunk_song_data(
    song: SongData,
    gap_threshold_sec: float = 5.0,
    min_chunk_lines: int = 2,
) -> list[LrcChunk]:
    """Chunk a SongData into sections.

    Uses section tags if present, otherwise falls back to temporal gap detection.
    Returns empty list if song has no lines.
    """
    if not song.lines:
        return []

    if has_section_tags(song.lines):
        chunks = chunk_by_tags(song.lines)
    else:
        chunks = chunk_by_gaps(song.lines, gap_threshold_sec=gap_threshold_sec, min_chunk_lines=min_chunk_lines)

    # Filter empty and add position metadata
    chunks = [c for c in chunks if c.lyrics.strip()]
    for i, chunk in enumerate(chunks):
        chunk.position = i
        chunk.total_chunks = len(chunks)

    return chunks
```

Note: the import of `SongData` at the top of `chunker.py` creates a potential circular import since `models.py` does not import from `chunker.py`. Add the import alongside the existing `from .models import LrcChunk, LrcLine, LrcLyric` line.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_chunker.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/resonance/chunker.py tests/test_chunker.py
git commit -m "feat: add chunk_song_data that accepts SongData instead of file path"
```

---

### Task 4: Build LibraryScanner — sidecar LRC extraction

Start with the sidecar LRC path since it mirrors current behavior and doesn't require mutagen lyrics parsing. This lets us validate the scanner architecture with known-good data.

**Files:**

- Create: `src/resonance/scanner.py`
- Create: `tests/test_scanner.py`

- [ ] **Step 1: Write tests for sidecar LRC extraction**

Create `tests/test_scanner.py`:

```python
"""Tests for LibraryScanner."""

from pathlib import Path

from resonance.scanner import LibraryScanner


def _write_lrc(directory: Path, stem: str, content: str) -> Path:
    """Write an LRC file and return its path."""
    lrc = directory / f"{stem}.lrc"
    lrc.write_text(content, encoding="utf-8")
    return lrc


def _write_audio(directory: Path, stem: str, suffix: str = ".flac") -> Path:
    """Write a dummy audio file and return its path."""
    audio = directory / f"{stem}{suffix}"
    audio.write_bytes(b"\x00" * 64)
    return audio


LRC_CONTENT = """[00:00.00] First line of the song
[00:05.50] Second line here
[00:10.00] Third line goes
[00:15.00] Fourth line ends
"""


class TestSidecarLrcExtraction:
    def test_finds_audio_with_sidecar_lrc(self, tmp_path):
        _write_audio(tmp_path, "01 - Coldplay - Fix You")
        _write_lrc(tmp_path, "01 - Coldplay - Fix You", LRC_CONTENT)

        scanner = LibraryScanner()
        results = list(scanner.scan(tmp_path))

        assert len(results) == 1
        song = results[0]
        assert song.filename == "01 - Coldplay - Fix You.flac"
        assert song.audio_path == tmp_path / "01 - Coldplay - Fix You.flac"
        assert len(song.lines) == 4
        assert song.lyrics_source == "sidecar_lrc"

    def test_skips_audio_without_lyrics(self, tmp_path):
        _write_audio(tmp_path, "no-lyrics-song")

        scanner = LibraryScanner()
        results = list(scanner.scan(tmp_path))
        assert len(results) == 0

    def test_skips_lrc_without_audio(self, tmp_path):
        _write_lrc(tmp_path, "orphan-lyrics", LRC_CONTENT)

        scanner = LibraryScanner()
        results = list(scanner.scan(tmp_path))
        assert len(results) == 0

    def test_scans_subdirectories(self, tmp_path):
        subdir = tmp_path / "Artist" / "Album"
        subdir.mkdir(parents=True)
        _write_audio(subdir, "01 - Track")
        _write_lrc(subdir, "01 - Track", LRC_CONTENT)

        scanner = LibraryScanner()
        results = list(scanner.scan(tmp_path))
        assert len(results) == 1

    def test_supports_multiple_audio_formats(self, tmp_path):
        for ext in [".mp3", ".flac", ".m4a", ".ogg", ".opus"]:
            stem = f"song{ext.replace('.', '')}"
            _write_audio(tmp_path, stem, suffix=ext)
            _write_lrc(tmp_path, stem, LRC_CONTENT)

        scanner = LibraryScanner()
        results = list(scanner.scan(tmp_path))
        assert len(results) == 5

    def test_metadata_from_filename_fallback(self, tmp_path):
        _write_audio(tmp_path, "03 - Coldplay - Ghost Story")
        _write_lrc(tmp_path, "03 - Coldplay - Ghost Story", LRC_CONTENT)

        scanner = LibraryScanner()
        results = list(scanner.scan(tmp_path))
        song = results[0]
        # Metadata from filename parsing (no real audio tags in dummy file)
        assert song.artist == "Coldplay"
        assert song.title == "Ghost Story"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_scanner.py -v`
Expected: FAIL — `LibraryScanner` not found

- [ ] **Step 3: Implement LibraryScanner with sidecar LRC support**

Create `src/resonance/scanner.py`:

```python
"""Library scanner — discovers audio files and extracts lyrics + metadata."""

import logging
import re
from collections.abc import Iterator
from pathlib import Path

import mutagen

from .models import LrcLine, SongData
from .parser import parse_lrc_lines

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".mp3", ".flac", ".m4a", ".ogg", ".opus"}


class LibraryScanner:
    """Scans a music directory for audio files and extracts lyrics.

    For each audio file, tries embedded synced lyrics first,
    then falls back to sidecar .lrc files.
    """

    def scan(self, path: Path) -> Iterator[SongData]:
        """Walk path recursively, yielding SongData for each song with lyrics."""
        audio_files = sorted(
            f for f in path.rglob("*") if f.suffix.lower() in SUPPORTED_EXTENSIONS
        )
        logger.info("Scanning %s, found %d audio files", path, len(audio_files))

        for audio_path in audio_files:
            song = self._extract_embedded(audio_path)
            if song is None:
                song = self._extract_sidecar_lrc(audio_path)
            if song is None:
                logger.debug("No lyrics found, skipping: %s", audio_path.name)
                continue
            yield song

    def _extract_embedded(self, audio_path: Path) -> SongData | None:
        """Try to extract synced lyrics from embedded audio tags.

        Placeholder — full implementation in Task 5.
        """
        return None

    def _extract_sidecar_lrc(self, audio_path: Path) -> SongData | None:
        """Look for a .lrc file with the same stem and extract lyrics."""
        lrc_path = audio_path.with_suffix(".lrc")
        if not lrc_path.exists():
            return None

        lines = parse_lrc_lines(lrc_path)
        if not lines:
            return None

        artist, title, album = _read_metadata(audio_path)
        logger.debug("Sidecar LRC found: %s", audio_path.name)

        return SongData(
            artist=artist,
            title=title,
            audio_path=audio_path,
            filename=audio_path.name,
            lines=lines,
            album=album,
            lyrics_source="sidecar_lrc",
        )


def _read_metadata(audio_path: Path) -> tuple[str, str, str | None]:
    """Read artist, title, album from audio tags. Fall back to filename parsing."""
    try:
        tags = mutagen.File(audio_path, easy=True)
    except Exception:  # noqa: BLE001
        tags = None

    tag_artist = _first_tag(tags, "artist") if tags else None
    tag_title = _first_tag(tags, "title") if tags else None
    tag_album = _first_tag(tags, "album") if tags else None

    if tag_artist and tag_title:
        return tag_artist, tag_title, tag_album

    # Fallback: parse from filename
    fb_artist, fb_title = _extract_metadata_from_filename(audio_path.stem)
    return tag_artist or fb_artist, tag_title or fb_title, tag_album


def _first_tag(tags: mutagen.FileType, key: str) -> str | None:
    """Get the first value for a tag key, or None."""
    values = tags.get(key)
    if values and len(values) > 0 and values[0].strip():
        return values[0].strip()
    return None


def _extract_metadata_from_filename(stem: str) -> tuple[str, str]:
    """Extract artist and title from filename stem.

    Pattern: '03 - Coldplay - Ghost Story'
    Same logic as the former LrcLyric._extract_metadata.
    """
    parts = re.split(r"\s*-\s*", stem, maxsplit=2)
    if len(parts) >= 3:
        artist, title = parts[1].strip(), parts[2].strip()
    elif len(parts) == 2:
        artist, title = parts[0].strip(), parts[1].strip()
    else:
        artist, title = "Unknown", stem

    title = re.sub(r"\s*\((?:Album Version|Explicit)\)\s*$", "", title)
    return artist, title
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_scanner.py -v`
Expected: ALL PASS

- [ ] **Step 5: Run linter**

Run: `uv run ruff check src/resonance/scanner.py --fix`
Expected: no errors (or auto-fixed)

- [ ] **Step 6: Commit**

```bash
git add src/resonance/scanner.py tests/test_scanner.py
git commit -m "feat: add LibraryScanner with sidecar LRC extraction"
```

---

### Task 5: LibraryScanner — embedded lyrics extraction

Implement `_extract_embedded` for the three tag systems: ID3 (MP3), Vorbis Comments (FLAC/OGG/Opus), and MP4 atoms (M4A/AAC).

**Files:**

- Modify: `src/resonance/scanner.py` (implement `_extract_embedded`)
- Modify: `tests/test_scanner.py` (add embedded lyrics tests)

**Reference docs the implementer must consult:**

- mutagen docs: https://mutagen.readthedocs.io/
- ID3v2 SYLT frame: mutagen exposes as `tags['SYLT::eng']` with `.text` being list of `(text, timestamp_ms)` tuples. `type` field: 1 = lyrics, 2 = karaoke.
- Vorbis/FLAC: `tags['lyrics']` or `tags['LYRICS']` — may contain LRC-formatted text with `[mm:ss.xx]` timestamps. Check for timestamps to determine synced vs unsynced.
- MP4: `tags['©lyr']` — same as Vorbis, may contain LRC-formatted text.

- [ ] **Step 1: Write tests for embedded lyrics extraction**

Add to `tests/test_scanner.py`:

```python
import logging
from unittest.mock import MagicMock, patch

import mutagen.mp3


class TestEmbeddedLyricsExtraction:
    def test_extracts_id3_sylt_lyrics(self, tmp_path):
        """Test MP3 with ID3 SYLT (synchronized lyrics) tag."""
        audio_path = tmp_path / "01 - Artist - Song.mp3"
        audio_path.write_bytes(b"\x00" * 64)

        # Use spec=mutagen.mp3.MP3 so isinstance checks pass naturally
        mock_tags = MagicMock(spec=mutagen.mp3.MP3)
        mock_sylt = MagicMock()
        mock_sylt.text = [("First line", 0), ("Second line", 5000), ("Third line", 10000)]
        mock_sylt.type = 1  # LYRICS (not karaoke)
        mock_tags.getall.return_value = [mock_sylt]
        mock_tags.get.side_effect = lambda k, default=None: {
            "TPE1": MagicMock(text=["Artist"]),
            "TIT2": MagicMock(text=["Song"]),
            "TALB": MagicMock(text=["Album"]),
        }.get(k, default)

        with patch("resonance.scanner.mutagen.File") as mock_file:
            mock_file.return_value = mock_tags
            scanner = LibraryScanner()
            song = scanner._extract_embedded(audio_path)

        assert song is not None
        assert song.lyrics_source == "embedded"
        assert len(song.lines) == 3
        assert song.lines[0].text == "First line"
        assert song.lines[0].timestamp_sec == 0.0
        assert song.lines[1].timestamp_sec == 5.0

    def test_skips_sylt_karaoke_type(self, tmp_path):
        """SYLT frames with type != 1 (karaoke, etc.) should be skipped."""
        audio_path = tmp_path / "karaoke.mp3"
        audio_path.write_bytes(b"\x00" * 64)

        mock_tags = MagicMock(spec=mutagen.mp3.MP3)
        mock_sylt = MagicMock()
        mock_sylt.text = [("Karaoke line", 0)]
        mock_sylt.type = 2  # KARAOKE, not LYRICS
        mock_tags.getall.return_value = [mock_sylt]

        with patch("resonance.scanner.mutagen.File") as mock_file:
            mock_file.return_value = mock_tags
            scanner = LibraryScanner()
            song = scanner._extract_embedded(audio_path)

        assert song is None

    def test_extracts_vorbis_lrc_lyrics(self, tmp_path):
        """Test FLAC with LRC-formatted text in LYRICS Vorbis comment."""
        audio_path = tmp_path / "song.flac"
        audio_path.write_bytes(b"\x00" * 64)

        lrc_text = "[00:00.00] First line\n[00:05.00] Second line\n[00:10.00] Third line"
        mock_tags = MagicMock()
        mock_tags.get.side_effect = lambda k, default=None: {
            "lyrics": [lrc_text],
            "artist": ["Artist"],
            "title": ["Song"],
            "album": ["Album"],
        }.get(k.lower(), default)

        with patch("resonance.scanner.mutagen.File") as mock_file:
            mock_file.return_value = mock_tags
            scanner = LibraryScanner()
            with patch.object(scanner, "_try_id3_sylt", return_value=None):
                song = scanner._extract_embedded(audio_path)

        assert song is not None
        assert len(song.lines) == 3
        assert song.lyrics_source == "embedded"

    def test_extracts_mp4_lrc_lyrics(self, tmp_path):
        """Test M4A with LRC-formatted text in ©lyr atom."""
        audio_path = tmp_path / "song.m4a"
        audio_path.write_bytes(b"\x00" * 64)

        lrc_text = "[00:00.00] MP4 line one\n[00:05.00] MP4 line two"
        mock_tags = MagicMock()
        mock_tags.get.side_effect = lambda k, default=None: {
            "\xa9lyr": [lrc_text],
            "\xa9ART": ["Artist"],
            "\xa9nam": ["Song"],
            "\xa9alb": ["Album"],
        }.get(k, default)
        mock_tags.getall.return_value = []  # No SYLT

        with patch("resonance.scanner.mutagen.File") as mock_file:
            mock_file.return_value = mock_tags
            scanner = LibraryScanner()
            with patch.object(scanner, "_try_id3_sylt", return_value=None):
                song = scanner._extract_embedded(audio_path)

        assert song is not None
        assert len(song.lines) == 2
        assert song.lyrics_source == "embedded"

    def test_skips_unsynced_lyrics_with_warning(self, tmp_path, caplog):
        """Unsynced lyrics (no timestamps) should be skipped with WARNING."""
        audio_path = tmp_path / "song.flac"
        audio_path.write_bytes(b"\x00" * 64)

        mock_tags = MagicMock()
        mock_tags.get.side_effect = lambda k, default=None: {
            "lyrics": ["Just plain text without timestamps"],
        }.get(k.lower(), default)
        mock_tags.getall.return_value = []

        with patch("resonance.scanner.mutagen.File") as mock_file:
            mock_file.return_value = mock_tags
            with caplog.at_level(logging.WARNING, logger="resonance.scanner"):
                scanner = LibraryScanner()
                with patch.object(scanner, "_try_id3_sylt", return_value=None):
                    song = scanner._extract_embedded(audio_path)

        assert song is None
        assert any("No synced lyrics (unsynced only, skipping)" in r.message for r in caplog.records)

    def test_skips_mp4_unsynced_lyrics_with_warning(self, tmp_path, caplog):
        """MP4 unsynced lyrics should also be skipped with WARNING."""
        audio_path = tmp_path / "song.m4a"
        audio_path.write_bytes(b"\x00" * 64)

        mock_tags = MagicMock()
        mock_tags.get.side_effect = lambda k, default=None: {
            "\xa9lyr": ["Plain text lyrics no timestamps"],
        }.get(k, default)
        mock_tags.getall.return_value = []

        with patch("resonance.scanner.mutagen.File") as mock_file:
            mock_file.return_value = mock_tags
            with caplog.at_level(logging.WARNING, logger="resonance.scanner"):
                scanner = LibraryScanner()
                with patch.object(scanner, "_try_id3_sylt", return_value=None):
                    song = scanner._extract_embedded(audio_path)

        assert song is None
        assert any("No synced lyrics (unsynced only, skipping)" in r.message for r in caplog.records)

    def test_returns_none_when_no_lyrics_tags(self, tmp_path):
        audio_path = tmp_path / "instrumental.flac"
        audio_path.write_bytes(b"\x00" * 64)

        mock_tags = MagicMock()
        mock_tags.get.return_value = None
        mock_tags.getall.return_value = []

        with patch("resonance.scanner.mutagen.File") as mock_file:
            mock_file.return_value = mock_tags
            scanner = LibraryScanner()
            song = scanner._extract_embedded(audio_path)

        assert song is None

    def test_returns_none_when_mutagen_returns_none(self, tmp_path):
        """mutagen.File returns None for unrecognized files."""
        audio_path = tmp_path / "mystery.flac"
        audio_path.write_bytes(b"\x00" * 64)

        with patch("resonance.scanner.mutagen.File", return_value=None):
            scanner = LibraryScanner()
            song = scanner._extract_embedded(audio_path)

        assert song is None
```

**Note:** These tests use mocks because creating real audio files with embedded SYLT tags is fragile. The mocks verify the tag-reading logic. The implementer should adjust mocks if the actual mutagen API differs, but the following behaviors must always be verified:

1. SYLT frames with `type == 1` produce `LrcLine` objects with timestamps in seconds (ms / 1000)
2. SYLT frames with `type != 1` are skipped
3. Vorbis/MP4 LRC-formatted text is parsed into `LrcLine` objects
4. Vorbis/MP4 plain text (no timestamps) returns None and logs WARNING
5. `mutagen.File` returning None returns None without exception

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_scanner.py::TestEmbeddedLyricsExtraction -v`
Expected: FAIL — methods not implemented or mock setup issues

- [ ] **Step 3: Implement \_extract_embedded**

Replace the placeholder `_extract_embedded` in `src/resonance/scanner.py` with the full implementation. The method should:

1. Call `mutagen.File(audio_path)` (NOT easy=True — need raw tags for SYLT)
2. Try `_try_id3_sylt(tags, audio_path)` — check for `SYLT` frames, filter by `type == 1`, convert `(text, timestamp_ms)` tuples to `LrcLine` objects (divide ms by 1000.0)
3. Try `_try_lrc_in_tag(tags, audio_path)` — check Vorbis `lyrics`/`LYRICS` and MP4 `©lyr` fields, run content through `parse_lrc_text()`, return None if no timestamps found
4. If no synced lyrics from either path, check if unsynced lyrics exist and log WARNING: `"No synced lyrics (unsynced only, skipping): {filename}"`
5. Read metadata: for ID3 use `TPE1`, `TIT2`, `TALB`; for Vorbis use `artist`, `title`, `album`; for MP4 use `©ART`, `©nam`, `©alb`. Fall back to filename parsing per field.

The implementer should consult the mutagen docs for the exact API for each tag type. Key points:

- `mutagen.File()` returns different types: `MP3`, `FLAC`, `OggVorbis`, `OggOpus`, `MP4`
- For ID3: `tags.getall("SYLT")` returns a list of SYLT frames
- For Vorbis: `tags.get("lyrics")` returns a list of strings (or None)
- For MP4: `tags.get("©lyr")` returns a list of strings (or None)
- Use `mutagen.File(path, easy=True)` separately for metadata reading (artist/title/album) since easy tags normalize the key names across formats

- [ ] **Step 4: Run all scanner tests**

Run: `uv run pytest tests/test_scanner.py -v`
Expected: ALL PASS

If mocks need adjustment to match the actual mutagen API, adjust them — but do not weaken assertions. All test behaviors listed in the Step 1 note must remain verified.

- [ ] **Step 5: Run linter**

Run: `uv run ruff check src/resonance/scanner.py --fix`
Expected: clean

- [ ] **Step 6: Commit**

```bash
git add src/resonance/scanner.py tests/test_scanner.py
git commit -m "feat: add embedded lyrics extraction (ID3 SYLT, Vorbis, MP4)"
```

---

### Task 6: Wire scanner into ingest pipeline

Replace the LRC-file-scanning loop in `run_ingest` with `LibraryScanner`, update the Qdrant payload, and remove dead code.

**Files:**

- Modify: `src/resonance/routes/ingest.py` (use LibraryScanner, new payload)
- Modify: `src/resonance/chunker.py` (remove `chunk_song`, remove `LrcLyric` import)
- Modify: `src/resonance/models.py` (remove `LrcLyric` class)
- Modify: `tests/test_routes.py` (update `TestIngestRoute.test_ingest_processes_lrc_files`)

- [ ] **Step 1: Update ingest test to use new scanner**

In `tests/test_routes.py`, replace `test_ingest_processes_lrc_files` with a direct `run_ingest` call (the old test patched `MUSIC_DIR` which no longer exists):

```python
def test_ingest_processes_audio_files(self, tmp_path):
    """Test that audio files with sidecar LRC are ingested via LibraryScanner."""
    _, mock_qdrant, mock_embedder = _make_test_client()
    mock_qdrant.get_collections.return_value = MagicMock(collections=[])

    # Create a test audio file + sidecar LRC
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

    # Verify new payload fields are present in upserted points
    upsert_call = mock_qdrant.upsert.call_args_list[-1]
    points = upsert_call.kwargs["points"]
    payload = points[0].payload
    assert "audio_path" in payload
    assert "lyrics_source" in payload
    assert payload["filename"].endswith(".flac")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_routes.py::TestIngestRoute::test_ingest_processes_lrc_files -v`
Expected: FAIL (import or signature mismatches)

- [ ] **Step 3: Refactor run_ingest to use LibraryScanner**

In `src/resonance/routes/ingest.py`:

1. Remove `from resonance.chunker import chunk_song`
2. Remove `MUSIC_DIR` constant. The `data_dir` parameter is now required when calling `run_ingest` — the route handler must pass a value from settings. Add a `data_dir` field to the config (or use an existing settings path). If `data_dir` is None, raise a clear error: `"data_dir is required — set it in config or pass via CLI"`.
3. Add imports: `from resonance.scanner import LibraryScanner` and `from resonance.chunker import chunk_song_data`
4. Replace the scanning loop in `run_ingest`:

```python
# OLD:
for lrc_file in sorted(source_dir.rglob("*.lrc")):
    lyric = chunk_song(lrc_file, gap_threshold_sec=gap_threshold)
    if not lyric or not lyric.chunks:
        skipped += 1
        continue
    files_processed += 1
    chunks_to_embed.extend(...)

# NEW:
scanner = LibraryScanner()
for song in scanner.scan(source_dir):
    chunks = chunk_song_data(song, gap_threshold_sec=gap_threshold, min_chunk_lines=min_lines)
    if not chunks:
        skipped += 1
        continue
    files_processed += 1
    chunks_to_embed.extend(
        {
            "artist": song.artist,
            "title": song.title,
            "album": song.album,
            "filename": song.filename,
            "audio_path": str(song.audio_path.relative_to(source_dir)),
            "lyrics_source": song.lyrics_source,
            "section": chunk.section_name,
            "position": chunk.position,
            "total_sections": chunk.total_chunks,
            "lyrics": chunk.lyrics,
            "start_sec": chunk.start_sec,
            "duration_sec": chunk.duration_sec,
        }
        for chunk in chunks
    )
```

5. In the Qdrant upsert payload, remove the `[:500]` lyrics truncation — store full chunk lyrics.
6. Add `audio_path`, `album`, `lyrics_source` to the payload dict in the `PointStruct`.
7. Pass `min_chunk_lines` directly with a hardcoded default of 2 in the function signature (same as `chunk_by_gaps` default). No settings field needed — just use `min_lines = min_chunk_lines if min_chunk_lines is not None else 2`.

- [ ] **Step 4: Run the ingest test**

Run: `uv run pytest tests/test_routes.py::TestIngestRoute -v`
Expected: ALL PASS

- [ ] **Step 5: Run all tests to check for regressions**

Run: `uv run pytest -v`
Expected: ALL PASS (some tests may need minor fixups for changed imports)

- [ ] **Step 6: Remove dead code**

1. In `src/resonance/models.py`: remove the entire `LrcLyric` class (lines 51-109)
2. In `src/resonance/chunker.py`: remove `chunk_song` function (lines 106-127), remove `LrcLyric` from the import line, add `SongData` to imports if not done in Task 3
3. Check for any other references to `LrcLyric` or `chunk_song`:

Run: `uv run ruff check src/ --fix`

- [ ] **Step 7: Run all tests again**

Run: `uv run pytest -v`
Expected: ALL PASS

- [ ] **Step 8: Run linter on all changed files**

Run: `uv run ruff check src/ --fix && uv run ruff format src/`
Expected: clean

- [ ] **Step 9: Commit**

```bash
git add src/resonance/routes/ingest.py src/resonance/chunker.py src/resonance/models.py tests/test_routes.py
git commit -m "refactor: wire LibraryScanner into ingest, remove LrcLyric and chunk_song"
```

---

### Task 7: Update SearchResult and CLI for new payload fields

The search endpoint and CLI need to handle the new payload fields (`audio_path`, `album`, `lyrics_source`). Add `audio_path` and `album` to `SearchResult` so they're available to future m3u generation.

**Files:**

- Modify: `src/resonance/routes/search.py` (add fields to SearchResult)
- Modify: `src/resonance/search.py` (update CLI output — remove `lyrics_preview` reference)
- Modify: `tests/test_routes.py` (update mock payloads in search tests)

- [ ] **Step 1: Update search test mock payloads**

In `tests/test_routes.py`, update all mock `point.payload` dicts in `TestSearchRoute` to include the new fields:

```python
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
```

Add an assertion for the new fields:

```python
assert data["results"][0]["audio_path"] == "Coldplay/X&Y/05 - Coldplay - Fix You.flac"
assert data["results"][0]["album"] == "X&Y"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_routes.py::TestSearchRoute -v`
Expected: FAIL — `audio_path` not in SearchResult

- [ ] **Step 3: Update SearchResult model**

In `src/resonance/routes/search.py`, add fields to `SearchResult`:

```python
class SearchResult(BaseModel):
    """A single search result."""

    artist: str
    title: str
    album: str | None = None
    score: float
    section: str
    position: int
    total_sections: int
    lyrics: str
    filename: str
    audio_path: str
    lyrics_source: str = "sidecar_lrc"
```

Update the `run_search` function to read the new fields from the Qdrant payload:

```python
result = SearchResult(
    artist=p["artist"],
    title=p["title"],
    album=p.get("album"),
    score=point.score,
    section=p["section"],
    position=p["position"],
    total_sections=p["total_sections"],
    lyrics=p["lyrics"],
    filename=p["filename"],
    audio_path=p.get("audio_path", ""),
    lyrics_source=p.get("lyrics_source", "sidecar_lrc"),
)
```

- [ ] **Step 4: Fix CLI search output**

In `src/resonance/search.py`, line 52 references `result.lyrics_preview` which doesn't exist on `SearchResult`. Change to:

```python
for line in result.lyrics.split("\n")[:2]:
    print(f"     | {line}")
```

- [ ] **Step 5: Run all tests**

Run: `uv run pytest -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add src/resonance/routes/search.py src/resonance/search.py tests/test_routes.py
git commit -m "feat: add audio_path and album to SearchResult for m3u support"
```

---

### Task 8: Update CLI help text and final cleanup

**Files:**

- Modify: `pyproject.toml` (add scanner.py to ruff config if needed)
- Modify: `src/resonance/ingest.py` (update CLI help text — no longer "LRC files")

- [ ] **Step 1: Update CLI help text**

In `src/resonance/ingest.py`, update the `--data-dir` help string:

```python
parser.add_argument(
    "--data-dir",
    type=Path,
    help="Directory containing audio files with lyrics (embedded or .lrc sidecar)",
)
```

Update the module docstring at the top:

```python
"""
Ingest song lyrics into Qdrant.

Pipeline: scan audio files → extract lyrics (embedded/sidecar) → chunk → embed → store in Qdrant
"""
```

- [ ] **Step 2: Run full test suite and linter**

Run: `uv run pytest -v && uv run ruff check src/ --fix && uv run ruff format src/`
Expected: ALL PASS, no lint errors

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml src/resonance/ingest.py
git commit -m "chore: update CLI help text and docstrings for scanner refactor"
```

- [ ] **Step 4: Final verification — run full suite**

Run: `uv run pytest -v`
Expected: ALL PASS

---

## Summary of Changes

| File                             | Action | Description                                         |
| -------------------------------- | ------ | --------------------------------------------------- |
| `pyproject.toml`                 | Modify | Add `mutagen` dependency                            |
| `src/resonance/models.py`        | Modify | Add `SongData`, remove `LrcLyric`                   |
| `src/resonance/parser.py`        | Modify | Add `parse_lrc_text(str)`                           |
| `src/resonance/chunker.py`       | Modify | Add `chunk_song_data`, remove `chunk_song`          |
| `src/resonance/scanner.py`       | Create | `LibraryScanner` with embedded + sidecar extraction |
| `src/resonance/routes/ingest.py` | Modify | Use scanner, new payload, remove `MUSIC_DIR`        |
| `src/resonance/routes/search.py` | Modify | Add `audio_path`, `album` to `SearchResult`         |
| `src/resonance/search.py`        | Modify | Fix `lyrics_preview` → `lyrics`                     |
| `src/resonance/ingest.py`        | Modify | Update CLI help text                                |
| `tests/test_models.py`           | Create | Tests for `SongData`, `parse_lrc_text`              |
| `tests/test_chunker.py`          | Create | Tests for `chunk_song_data`                         |
| `tests/test_scanner.py`          | Create | Tests for `LibraryScanner`                          |
| `tests/test_routes.py`           | Modify | Update mock payloads, fix ingest test               |
