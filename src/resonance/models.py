"""Domain models for LRC lyrics processing."""

import re
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


@dataclass
class LrcLyric:
    """A complete song's lyrics with metadata, parsed from an LRC file.

    Holds both the raw parsed lines and the chunked sections,
    along with metadata extracted from the filename.
    """

    artist: str
    title: str
    filename: str
    lines: list[LrcLine] = field(default_factory=list)
    chunks: list[LrcChunk] = field(default_factory=list)

    @property
    def full_lyrics(self) -> str:
        return "\n".join(line.text for line in self.lines if line.text)

    @property
    def duration_sec(self) -> float:
        if not self.lines:
            return 0
        return self.lines[-1].timestamp_sec - self.lines[0].timestamp_sec

    @classmethod
    def from_file(cls, filepath: Path) -> LrcLyric | None:
        """Create an LrcLyric from an LRC file, extracting metadata from filename."""
        from .parser import parse_lrc_lines

        lines = parse_lrc_lines(filepath)
        if not lines:
            return None

        artist, title = cls._extract_metadata(filepath)

        return cls(
            artist=artist,
            title=title,
            filename=filepath.name,
            lines=lines,
        )

    @staticmethod
    def _extract_metadata(filepath: Path) -> tuple[str, str]:
        """Extract artist and title from filename.

        Pattern: "03 - Coldplay - Ghost Story.lrc"
        """
        name = filepath.stem
        parts = re.split(r"\s*-\s*", name, maxsplit=2)
        if len(parts) >= 3:
            artist, title = parts[1].strip(), parts[2].strip()
        elif len(parts) == 2:
            artist, title = parts[0].strip(), parts[1].strip()
        else:
            artist, title = "Unknown", name

        title = re.sub(r"\s*\((?:Album Version|Explicit)\)\s*$", "", title)
        return artist, title
