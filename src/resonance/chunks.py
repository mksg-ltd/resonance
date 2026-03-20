"""
Visualize how a song gets chunked.

Usage:
    uv run resonance-chunks "path/to/song.lrc"
    uv run resonance-chunks "path/to/song.lrc" --gap 8.0
"""

from argparse import ArgumentParser
from pathlib import Path

from .chunker import chunk_song_data
from .models import SongData
from .parser import parse_lrc_lines


def main():
    parser = ArgumentParser(description="Visualize chunking for an LRC file")
    parser.add_argument("file", type=Path, help="Path to LRC file")
    parser.add_argument("--gap", type=float, default=5.0, help="Gap threshold in seconds")
    args = parser.parse_args()

    if not args.file.exists():
        print(f"File not found: {args.file}")
        return

    lines = parse_lrc_lines(args.file)
    if not lines:
        print(f"Could not parse: {args.file}")
        return

    song = SongData(
        artist="Unknown",
        title=args.file.stem,
        audio_path=args.file,
        filename=args.file.name,
        lines=lines,
    )
    chunks = chunk_song_data(song, gap_threshold_sec=args.gap)
    if not chunks:
        print(f"No chunks produced: {args.file}")
        return

    total_duration = lines[-1].timestamp_sec - lines[0].timestamp_sec if lines else 0
    print(f"\n  {song.artist} — {song.title}")
    print(f"  {song.filename}")
    print(f"  Duration: {total_duration:.1f}s | Chunks: {len(chunks)} | Gap threshold: {args.gap}s")
    print(f"  {'─' * 60}")

    for chunk in chunks:
        print(f"\n  [{chunk.section_name}] (part {chunk.position + 1}/{chunk.total_chunks})")
        print(f"  {chunk.start_sec:.1f}s → {chunk.end_sec:.1f}s ({chunk.duration_sec:.1f}s)")
        print()
        for line in chunk.lines:
            if line.text:
                print(f"    {line.timestamp_str}  {line.text}")
            else:
                print(f"    {line.timestamp_str}  ···")

    print(f"\n  {'─' * 60}")
    print(f"  Total: {len(chunks)} chunks, {len(lines)} lines\n")


if __name__ == "__main__":
    main()
