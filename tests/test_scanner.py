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
