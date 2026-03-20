"""Domain models for LRC lyrics processing."""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class LrcLine:
    """A single timestamped line from an LRC file."""

    timestamp_sec: float
    text: str

    @property
    def timestamp_str(self) -> str:
        mins, secs = divmod(self.timestamp_sec, 60)
        return f"{int(mins):02d}:{secs:05.2f}"


@dataclass
class LrcChunk:
    """A section of a song — verse, chorus, bridge, etc.

    A chunk is a group of consecutive LrcLines that belong to
    the same structural section of a song.
    """

    section_name: str
    lines: list[LrcLine] = field(default_factory=list)
    position: int = 0
    total_chunks: int = 0

    @property
    def lyrics(self) -> str:
        return "\n".join(line.text for line in self.lines if line.text)

    @property
    def start_sec(self) -> float:
        return self.lines[0].timestamp_sec if self.lines else 0

    @property
    def end_sec(self) -> float:
        return self.lines[-1].timestamp_sec if self.lines else 0

    @property
    def duration_sec(self) -> float:
        return self.end_sec - self.start_sec


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
