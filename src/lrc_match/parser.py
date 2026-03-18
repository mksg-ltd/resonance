"""LRC file parsing — extract timestamped lines from LRC format."""

import re
from pathlib import Path

from .models import LrcLine

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
        if len(frac) == 2:
            frac_sec = int(frac) / 100
        else:
            frac_sec = int(frac) / 1000
        timestamp = mins * 60 + secs + frac_sec
        text_content = m.group(4).strip()
        lines.append(LrcLine(timestamp_sec=timestamp, text=text_content))

    return lines
