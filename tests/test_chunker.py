"""Tests for chunking logic."""

from resonance.chunker import chunk_song_data
from resonance.models import LrcLine, Track


def _make_song(lines: list[LrcLine], artist: str = "Test", title: str = "Song") -> Track:
    return Track(source_id="test", library_id="1", song_id="song-1", artist=artist, title=title, lines=lines)


class TestChunkSongData:
    def test_chunks_by_time_gaps(self):
        lines = [
            LrcLine(0.0, "Line one"),
            LrcLine(2.0, "Line two"),
            LrcLine(3.0, "Line three"),
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
            LrcLine(10.0, "B"),
            LrcLine(20.0, "C"),
            LrcLine(22.0, "D"),
            LrcLine(24.0, "E"),
        ]
        song = _make_song(lines)
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
        for chunk in chunks:
            assert chunk.lyrics.strip() != ""
