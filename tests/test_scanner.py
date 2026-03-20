"""Tests for LibraryScanner."""

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import mutagen.flac
import mutagen.mp3
import mutagen.mp4

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


class TestEmbeddedLyricsExtraction:
    """Tests for _extract_embedded — uses mocks since creating real tagged audio is complex."""

    def _make_scanner(self) -> LibraryScanner:
        return LibraryScanner()

    def test_sylt_type1_produces_lrc_lines(self, tmp_path):
        """SYLT frames with type==1 (LYRICS) produce LrcLines with timestamps in seconds."""
        audio_path = tmp_path / "song.mp3"
        audio_path.write_bytes(b"\x00" * 64)

        sylt_frame = MagicMock()
        sylt_frame.type = 1
        sylt_frame.text = [("First line", 0), ("Second line", 5500), ("Third line", 10000)]

        mock_tags = MagicMock(spec=mutagen.mp3.MP3)
        mock_tags.tags = {"SYLT::eng": sylt_frame}
        mock_tags.keys = mock_tags.tags.keys
        mock_tags.__getitem__ = mock_tags.tags.__getitem__
        mock_tags.__contains__ = mock_tags.tags.__contains__
        mock_tags.items = mock_tags.tags.items

        with (
            patch("resonance.scanner.mutagen.File", return_value=mock_tags),
            patch("resonance.scanner._read_metadata", return_value=("Artist", "Title", "Album")),
        ):
            scanner = self._make_scanner()
            result = scanner._extract_embedded(audio_path)

        assert result is not None
        assert len(result.lines) == 3
        assert result.lines[0].timestamp_sec == 0.0
        assert result.lines[0].text == "First line"
        assert result.lines[1].timestamp_sec == 5.5
        assert result.lines[2].timestamp_sec == 10.0
        assert result.lyrics_source == "embedded"

    def test_sylt_type_not1_is_skipped(self, tmp_path):
        """SYLT frames with type!=1 (e.g. karaoke) are skipped."""
        audio_path = tmp_path / "song.mp3"
        audio_path.write_bytes(b"\x00" * 64)

        sylt_frame = MagicMock()
        sylt_frame.type = 2  # karaoke, not lyrics
        sylt_frame.text = [("Word", 0)]

        mock_tags = MagicMock(spec=mutagen.mp3.MP3)
        mock_tags.tags = {"SYLT::eng": sylt_frame}
        mock_tags.keys = mock_tags.tags.keys
        mock_tags.__getitem__ = mock_tags.tags.__getitem__
        mock_tags.__contains__ = mock_tags.tags.__contains__
        mock_tags.items = mock_tags.tags.items

        with patch("resonance.scanner.mutagen.File", return_value=mock_tags):
            scanner = self._make_scanner()
            result = scanner._extract_embedded(audio_path)

        assert result is None

    def test_vorbis_lrc_text_parsed(self, tmp_path):
        """Vorbis comments with LRC-formatted lyrics text are parsed into LrcLines."""
        audio_path = tmp_path / "song.flac"
        audio_path.write_bytes(b"\x00" * 64)

        lrc_text = "[00:00.00] Hello world\n[00:05.50] Second line\n"

        mock_tags = MagicMock(spec=mutagen.flac.FLAC)
        mock_tags.tags = {"lyrics": [lrc_text]}
        mock_tags.keys = mock_tags.tags.keys
        mock_tags.__getitem__ = mock_tags.tags.__getitem__
        mock_tags.__contains__ = mock_tags.tags.__contains__
        mock_tags.get = mock_tags.tags.get

        with (
            patch("resonance.scanner.mutagen.File", return_value=mock_tags),
            patch("resonance.scanner._read_metadata", return_value=("Artist", "Title", None)),
        ):
            scanner = self._make_scanner()
            result = scanner._extract_embedded(audio_path)

        assert result is not None
        assert len(result.lines) == 2
        assert result.lines[0].text == "Hello world"
        assert result.lines[1].timestamp_sec == 5.5
        assert result.lyrics_source == "embedded"

    def test_mp4_lrc_text_parsed(self, tmp_path):
        """MP4 ©lyr tag with LRC-formatted text is parsed into LrcLines."""
        audio_path = tmp_path / "song.m4a"
        audio_path.write_bytes(b"\x00" * 64)

        lrc_text = "[00:00.00] Hello world\n[00:05.50] Second line\n"

        mock_tags = MagicMock(spec=mutagen.mp4.MP4)
        mock_tags.tags = {"©lyr": [lrc_text]}
        mock_tags.keys = mock_tags.tags.keys
        mock_tags.__getitem__ = mock_tags.tags.__getitem__
        mock_tags.__contains__ = mock_tags.tags.__contains__
        mock_tags.get = mock_tags.tags.get

        with (
            patch("resonance.scanner.mutagen.File", return_value=mock_tags),
            patch("resonance.scanner._read_metadata", return_value=("Artist", "Title", "Album")),
        ):
            scanner = self._make_scanner()
            result = scanner._extract_embedded(audio_path)

        assert result is not None
        assert len(result.lines) == 2
        assert result.lyrics_source == "embedded"

    def test_vorbis_plain_text_skips_with_warning(self, tmp_path, caplog):
        """Plain text lyrics (no timestamps) in Vorbis returns None and logs WARNING."""
        audio_path = tmp_path / "song.flac"
        audio_path.write_bytes(b"\x00" * 64)

        plain_text = "Just some lyrics without timestamps\nAnother line\n"

        mock_tags = MagicMock(spec=mutagen.flac.FLAC)
        mock_tags.tags = {"lyrics": [plain_text]}
        mock_tags.keys = mock_tags.tags.keys
        mock_tags.__getitem__ = mock_tags.tags.__getitem__
        mock_tags.__contains__ = mock_tags.tags.__contains__
        mock_tags.get = mock_tags.tags.get
        mock_tags.items = mock_tags.tags.items

        with (
            caplog.at_level(logging.WARNING, logger="resonance.scanner"),
            patch("resonance.scanner.mutagen.File", return_value=mock_tags),
        ):
            scanner = self._make_scanner()
            result = scanner._extract_embedded(audio_path)

        assert result is None
        assert any("No synced lyrics (unsynced only, skipping)" in r.message for r in caplog.records)

    def test_mp4_plain_text_skips_with_warning(self, tmp_path, caplog):
        """Plain text lyrics (no timestamps) in MP4 returns None and logs WARNING."""
        audio_path = tmp_path / "song.m4a"
        audio_path.write_bytes(b"\x00" * 64)

        plain_text = "Just some lyrics without timestamps\nAnother line\n"

        mock_tags = MagicMock(spec=mutagen.mp4.MP4)
        mock_tags.tags = {"©lyr": [plain_text]}
        mock_tags.keys = mock_tags.tags.keys
        mock_tags.__getitem__ = mock_tags.tags.__getitem__
        mock_tags.__contains__ = mock_tags.tags.__contains__
        mock_tags.get = mock_tags.tags.get
        mock_tags.items = mock_tags.tags.items

        with (
            caplog.at_level(logging.WARNING, logger="resonance.scanner"),
            patch("resonance.scanner.mutagen.File", return_value=mock_tags),
        ):
            scanner = self._make_scanner()
            result = scanner._extract_embedded(audio_path)

        assert result is None
        assert any("No synced lyrics (unsynced only, skipping)" in r.message for r in caplog.records)

    def test_no_lyrics_tags_returns_none(self, tmp_path):
        """Audio file with no lyrics tags returns None."""
        audio_path = tmp_path / "song.flac"
        audio_path.write_bytes(b"\x00" * 64)

        mock_tags = MagicMock(spec=mutagen.flac.FLAC)
        mock_tags.tags = {}
        mock_tags.keys = mock_tags.tags.keys
        mock_tags.__getitem__ = mock_tags.tags.__getitem__
        mock_tags.__contains__ = mock_tags.tags.__contains__
        mock_tags.get = mock_tags.tags.get
        mock_tags.items = mock_tags.tags.items

        with patch("resonance.scanner.mutagen.File", return_value=mock_tags):
            scanner = self._make_scanner()
            result = scanner._extract_embedded(audio_path)

        assert result is None

    def test_mutagen_file_returns_none(self, tmp_path):
        """mutagen.File returning None (unrecognized file) returns None."""
        audio_path = tmp_path / "song.xyz"
        audio_path.write_bytes(b"\x00" * 64)

        with patch("resonance.scanner.mutagen.File", return_value=None):
            scanner = self._make_scanner()
            result = scanner._extract_embedded(audio_path)

        assert result is None
