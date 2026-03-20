"""
Chunk LRC lyrics into song sections.

Two strategies, applied in priority order:
1. Explicit section tags: [Chorus], [Verse 1], [Bridge], etc.
2. Temporal gap detection: large time gaps between lines indicate section boundaries.
"""

import re

from .models import LrcChunk, LrcLine, SongData

# Matches section tags like [Chorus], [Verse 1-Akon], [Bridge], [Outro]
SECTION_TAG_RE = re.compile(
    r"\[(Verse|Chorus|Bridge|Intro|Outro|Hook|Pre-Chorus|Interlude|Refrain|Solo)"
    r"[^\]]*\]",
    re.IGNORECASE,
)


def has_section_tags(lines: list[LrcLine]) -> bool:
    """Check if any lines contain explicit section markers."""
    return any(SECTION_TAG_RE.search(line.text) for line in lines)


def chunk_by_tags(lines: list[LrcLine]) -> list[LrcChunk]:
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
            if current_lines and any(line_.text for line_ in current_lines):
                chunks.append(LrcChunk(section_name=current_name, lines=current_lines))
            current_name = tag_match.group(0).strip("[]")
            cleaned_text = SECTION_TAG_RE.sub("", line.text).strip()
            current_lines = [LrcLine(line.timestamp_sec, cleaned_text)]
        else:
            current_lines.append(line)

    if current_lines and any(line_.text for line_ in current_lines):
        chunks.append(LrcChunk(section_name=current_name, lines=current_lines))

    return chunks


def chunk_by_gaps(
    lines: list[LrcLine],
    gap_threshold_sec: float = 5.0,
    min_chunk_lines: int = 2,
) -> list[LrcChunk]:
    """Split lyrics at large temporal gaps between lines.

    This mirrors the conversation grouping algorithm:
    - Lines are "messages"
    - Time gaps between lines are "conversation gaps"
    - Sections are "conversations"
    """
    if not lines:
        return []

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

    # Merge tiny chunks into neighbors
    merged = []
    for chunk_lines in raw_chunks:
        content_lines = [line_ for line_ in chunk_lines if line_.text]
        if len(content_lines) < min_chunk_lines and merged:
            merged[-1].extend(chunk_lines)
        else:
            merged.append(chunk_lines)

    chunks = []
    for i, chunk_lines in enumerate(merged):
        position_ratio = i / max(len(merged) - 1, 1)
        if i == 0:
            name = "Opening"
        elif position_ratio > 0.85:
            name = "Closing"
        else:
            name = f"Section {i + 1}"

        chunks.append(LrcChunk(section_name=name, lines=chunk_lines))

    return chunks


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
