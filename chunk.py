"""
Chunk LRC lyrics into song sections.

Two strategies, applied in priority order:
1. Explicit section tags: [Chorus], [Verse 1], [Bridge], etc.
2. Temporal gap detection: large time gaps between lines indicate section boundaries.

This is the same problem as conversation grouping — given a sequence of
timestamped items, find natural boundaries that divide them into meaningful groups.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class LrcLine:
    """A single line from an LRC file with its timestamp."""
    timestamp_sec: float  # absolute time in seconds
    text: str

    @property
    def timestamp_str(self) -> str:
        mins, secs = divmod(self.timestamp_sec, 60)
        return f"{int(mins):02d}:{secs:05.2f}"


@dataclass
class SongChunk:
    """A section of a song — verse, chorus, bridge, etc."""
    section_name: str          # "Verse 1", "Chorus", "Section 3" (inferred)
    lines: list[LrcLine] = field(default_factory=list)
    position: int = 0         # 0-indexed position within the song
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


# --- Parsing ---

# Matches section tags like [Chorus], [Verse 1-Akon], [Bridge], [Outro]
SECTION_TAG_RE = re.compile(
    r"\[(Verse|Chorus|Bridge|Intro|Outro|Hook|Pre-Chorus|Interlude|Refrain|Solo)"
    r"[^\]]*\]",
    re.IGNORECASE,
)

# Matches LRC timestamp lines: [00:32.27] lyrics here
TIMESTAMP_RE = re.compile(r"\[(\d{2}):(\d{2})\.(\d{2,3})\]\s*(.*)")


def parse_lrc_lines(filepath: Path) -> list[LrcLine]:
    """Parse an LRC file into timestamped lines."""
    try:
        text = filepath.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []

    lines = []
    for raw_line in text.splitlines():
        m = TIMESTAMP_RE.match(raw_line.strip())
        if not m:
            continue
        mins, secs, frac = int(m.group(1)), int(m.group(2)), m.group(3)
        # Handle both .XX and .XXX formats
        if len(frac) == 2:
            frac_sec = int(frac) / 100
        else:
            frac_sec = int(frac) / 1000
        timestamp = mins * 60 + secs + frac_sec
        text_content = m.group(4).strip()
        lines.append(LrcLine(timestamp_sec=timestamp, text=text_content))

    return lines


def has_section_tags(lines: list[LrcLine]) -> bool:
    """Check if any lines contain explicit section markers."""
    return any(SECTION_TAG_RE.search(line.text) for line in lines)


# --- Strategy 1: Section tag chunking ---

def chunk_by_tags(lines: list[LrcLine]) -> list[SongChunk]:
    """Split lyrics at explicit section tags like [Chorus], [Verse 1].

    When we encounter a section tag, it starts a new chunk.
    Lines before the first tag go into an "Intro" chunk.
    """
    chunks = []
    current_lines = []
    current_name = "Intro"

    for line in lines:
        tag_match = SECTION_TAG_RE.search(line.text)
        if tag_match:
            # Save previous chunk if it has content
            if current_lines and any(l.text for l in current_lines):
                chunks.append(SongChunk(section_name=current_name, lines=current_lines))
            # Start new chunk — strip the tag from the line text
            current_name = tag_match.group(0).strip("[]")
            cleaned_text = SECTION_TAG_RE.sub("", line.text).strip()
            current_lines = [LrcLine(line.timestamp_sec, cleaned_text)]
        else:
            current_lines.append(line)

    # Don't forget the last chunk
    if current_lines and any(l.text for l in current_lines):
        chunks.append(SongChunk(section_name=current_name, lines=current_lines))

    return chunks


# --- Strategy 2: Temporal gap chunking ---

def chunk_by_gaps(
    lines: list[LrcLine],
    gap_threshold_sec: float = 5.0,
    min_chunk_lines: int = 2,
) -> list[SongChunk]:
    """Split lyrics at large temporal gaps between lines.

    This mirrors the conversation grouping algorithm:
    - Lines are "messages"
    - Time gaps between lines are "conversation gaps"
    - Sections are "conversations"

    gap_threshold_sec: minimum gap (in seconds) to consider a section boundary.
      Why 5 seconds? Most lyric lines are 1-3 seconds apart. A 5+ second gap
      usually means an instrumental break, key change, or structural shift.

    min_chunk_lines: merge tiny chunks back into neighbors.
      A "section" with 1 line is probably not a real section — it's a
      transitional line or ad-lib that shouldn't be its own embedding.
    """
    if not lines:
        return []

    # First pass: split at gaps
    raw_chunks = []
    current_lines = [lines[0]]

    for i in range(1, len(lines)):
        gap = lines[i].timestamp_sec - lines[i - 1].timestamp_sec

        if gap >= gap_threshold_sec:
            raw_chunks.append(current_lines)
            current_lines = [lines[i]]
        else:
            current_lines.append(lines[i])

    raw_chunks.append(current_lines)

    # Second pass: merge tiny chunks into neighbors
    # A 1-line chunk between two real sections is noise, not structure
    merged = []
    for chunk_lines in raw_chunks:
        content_lines = [l for l in chunk_lines if l.text]
        if len(content_lines) < min_chunk_lines and merged:
            # Too small — merge into previous chunk
            merged[-1].extend(chunk_lines)
        else:
            merged.append(chunk_lines)

    # Build SongChunk objects with inferred names
    chunks = []
    for i, chunk_lines in enumerate(merged):
        # Name based on position in song structure
        position_ratio = i / max(len(merged) - 1, 1)
        if i == 0:
            name = "Opening"
        elif position_ratio > 0.85:
            name = "Closing"
        elif position_ratio < 0.4:
            name = f"Section {i + 1}"
        else:
            name = f"Section {i + 1}"

        chunks.append(SongChunk(section_name=name, lines=chunk_lines))

    return chunks


# --- Main entry point ---

def chunk_song(filepath: Path, gap_threshold_sec: float = 5.0) -> list[SongChunk]:
    """Chunk a song into sections using the best available strategy.

    Returns a list of SongChunks with position metadata.
    """
    lines = parse_lrc_lines(filepath)
    if not lines:
        return []

    # Pick strategy
    if has_section_tags(lines):
        chunks = chunk_by_tags(lines)
    else:
        chunks = chunk_by_gaps(lines, gap_threshold_sec=gap_threshold_sec)

    # Filter out empty chunks and add position metadata
    chunks = [c for c in chunks if c.lyrics.strip()]
    for i, chunk in enumerate(chunks):
        chunk.position = i
        chunk.total_chunks = len(chunks)

    return chunks


# --- CLI for testing ---

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python chunk.py <lrc_file> [gap_threshold_sec]")
        sys.exit(1)

    filepath = Path(sys.argv[1])
    threshold = float(sys.argv[2]) if len(sys.argv) > 2 else 5.0

    chunks = chunk_song(filepath, gap_threshold_sec=threshold)

    strategy = "section tags" if has_section_tags(parse_lrc_lines(filepath)) else "temporal gaps"
    print(f"Strategy: {strategy}")
    print(f"Chunks: {len(chunks)}\n")

    for chunk in chunks:
        print(f"--- [{chunk.section_name}] ({chunk.start_sec:.1f}s - {chunk.end_sec:.1f}s, {len(chunk.lines)} lines) ---")
        # Show first 3 and last line
        display_lines = chunk.lyrics.split("\n")
        if len(display_lines) > 5:
            for line in display_lines[:3]:
                print(f"  {line}")
            print(f"  ... ({len(display_lines) - 4} more lines)")
            print(f"  {display_lines[-1]}")
        else:
            for line in display_lines:
                print(f"  {line}")
        print()
