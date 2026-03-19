"""
Visualize how a song gets chunked.

Usage:
    uv run lrc-chunks "path/to/song.lrc"
    uv run lrc-chunks "path/to/song.lrc" --gap 8.0
"""

from argparse import ArgumentParser
from pathlib import Path

from .chunker import chunk_song


def main():
    parser = ArgumentParser(description="Visualize chunking for an LRC file")
    parser.add_argument("file", type=Path, help="Path to LRC file")
    parser.add_argument("--gap", type=float, default=5.0, help="Gap threshold in seconds")
    args = parser.parse_args()

    if not args.file.exists():
        print(f"File not found: {args.file}")
        return

    lyric = chunk_song(args.file, gap_threshold_sec=args.gap)
    if not lyric:
        print(f"Could not parse: {args.file}")
        return

    print(f"\n  {lyric.artist} — {lyric.title}")
    print(f"  {lyric.filename}")
    print(f"  Duration: {lyric.duration_sec:.1f}s | Chunks: {len(lyric.chunks)} | Gap threshold: {args.gap}s")
    print(f"  {'─' * 60}")

    for chunk in lyric.chunks:
        print(f"\n  [{chunk.section_name}] (part {chunk.position + 1}/{chunk.total_chunks})")
        print(f"  {chunk.start_sec:.1f}s → {chunk.end_sec:.1f}s ({chunk.duration_sec:.1f}s)")
        print()
        for line in chunk.lines:
            if line.text:
                print(f"    {line.timestamp_str}  {line.text}")
            else:
                print(f"    {line.timestamp_str}  ···")

    print(f"\n  {'─' * 60}")
    print(f"  Total: {len(lyric.chunks)} chunks, {len(lyric.lines)} lines\n")


if __name__ == "__main__":
    main()
