"""Domain models for lyrics and library tracks."""

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
class Track:
    """A server-scoped recording; no local filesystem access is required."""

    source_id: str
    library_id: str
    song_id: str
    artist: str
    title: str
    album: str | None = None
    lines: list[LrcLine] = field(default_factory=list, repr=False)
    lyrics_status: str = "not_loaded"
    language: str | None = None
    offset_ms: float = 0


@dataclass
class Library:
    """A library visible to the configured account."""

    id: str
    name: str


@dataclass
class ConnectionInfo:
    """Non-secret server identity and negotiated capabilities."""

    server_type: str
    server_version: str
    protocol_version: str
    extensions: dict[str, list[int]] = field(default_factory=dict)


@dataclass
class ServerPlaylist:
    """An exact server playlist snapshot, including explicit visibility."""

    id: str
    name: str
    owner: str
    public: bool | None
    song_count: int
    song_ids: list[str]
