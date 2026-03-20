"""Tests for domain models."""

from pathlib import Path

from resonance.models import LrcLine, SongData
from resonance.parser import parse_lrc_text


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
