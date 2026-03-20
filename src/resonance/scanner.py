"""Library scanner — discovers audio files and extracts lyrics + metadata."""

import logging
import re
from collections.abc import Iterator
from pathlib import Path

import mutagen
import mutagen.flac
import mutagen.mp3
import mutagen.mp4
import mutagen.oggopus
import mutagen.oggvorbis

from .models import LrcLine, SongData
from .parser import parse_lrc_lines, parse_lrc_text

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".mp3", ".flac", ".m4a", ".ogg", ".opus"}


class LibraryScanner:
    """Scans a music directory for audio files and extracts lyrics.

    For each audio file, tries embedded synced lyrics first,
    then falls back to sidecar .lrc files.
    """

    def scan(self, path: Path) -> Iterator[SongData]:
        """Walk path recursively, yielding SongData for each song with lyrics."""
        audio_files = sorted(f for f in path.rglob("*") if f.suffix.lower() in SUPPORTED_EXTENSIONS)
        logger.info("Scanning %s, found %d audio files", path, len(audio_files))

        for audio_path in audio_files:
            song = self._extract_embedded(audio_path)
            if song is None:
                song = self._extract_sidecar_lrc(audio_path)
            if song is None:
                logger.debug("No lyrics found, skipping: %s", audio_path.name)
                continue
            yield song

    def _extract_embedded(self, audio_path: Path) -> SongData | None:
        """Try to extract synced lyrics from embedded audio tags.

        Supports ID3v2 SYLT frames (MP3), Vorbis comments (FLAC/OGG/Opus),
        and MP4/iTunes tags (M4A/AAC).
        """
        try:
            tags = mutagen.File(audio_path)
        except Exception:  # noqa: BLE001
            return None

        if tags is None:
            return None

        # Try ID3 SYLT (MP3)
        result = self._try_id3_sylt(tags, audio_path)
        if result is not None:
            return result

        # Try Vorbis/MP4 lyrics fields
        return self._try_lrc_in_tag(tags, audio_path)

    def _try_id3_sylt(self, tags: mutagen.FileType, audio_path: Path) -> SongData | None:
        """Extract synced lyrics from ID3v2 SYLT frames (MP3 files)."""
        if not isinstance(tags, mutagen.mp3.MP3):
            return None

        for key, frame in tags.items():
            if not key.startswith("SYLT"):
                continue
            if frame.type != 1:
                logger.debug("Skipping SYLT frame with type=%d (not lyrics): %s", frame.type, audio_path.name)
                continue

            lines = [LrcLine(timestamp_sec=ts_ms / 1000.0, text=text) for text, ts_ms in frame.text]
            if not lines:
                continue

            artist, title, album = _read_metadata(audio_path)
            logger.debug("Embedded ID3 SYLT found: %s", audio_path.name)
            return SongData(
                artist=artist,
                title=title,
                audio_path=audio_path,
                filename=audio_path.name,
                lines=lines,
                album=album,
                lyrics_source="embedded_id3_sylt",
            )

        return None

    def _try_lrc_in_tag(self, tags: mutagen.FileType, audio_path: Path) -> SongData | None:
        """Extract LRC-formatted lyrics from Vorbis comments or MP4 tags."""
        text: str | None = None
        source: str | None = None

        if isinstance(tags, mutagen.flac.FLAC | mutagen.oggvorbis.OggVorbis | mutagen.oggopus.OggOpus):
            for key in ("lyrics", "LYRICS"):
                values = tags.get(key)
                if values:
                    text = values[0]
                    source = "embedded_vorbis"
                    break
        elif isinstance(tags, mutagen.mp4.MP4):
            values = tags.get("©lyr")
            if values:
                text = values[0]
                source = "embedded_mp4"

        if text is None:
            return None

        lines = parse_lrc_text(text)
        if not lines:
            # Has lyrics text but no timestamps — unsynced only
            logger.warning("No synced lyrics (unsynced only, skipping): %s", audio_path.name)
            return None

        artist, title, album = _read_metadata(audio_path)
        logger.debug("Embedded %s lyrics found: %s", source, audio_path.name)
        return SongData(
            artist=artist,
            title=title,
            audio_path=audio_path,
            filename=audio_path.name,
            lines=lines,
            album=album,
            lyrics_source=source,  # type: ignore[arg-type]
        )

    def _extract_sidecar_lrc(self, audio_path: Path) -> SongData | None:
        """Look for a .lrc file with the same stem and extract lyrics."""
        lrc_path = audio_path.with_suffix(".lrc")
        if not lrc_path.exists():
            return None

        lines = parse_lrc_lines(lrc_path)
        if not lines:
            return None

        artist, title, album = _read_metadata(audio_path)
        logger.debug("Sidecar LRC found: %s", audio_path.name)

        return SongData(
            artist=artist,
            title=title,
            audio_path=audio_path,
            filename=audio_path.name,
            lines=lines,
            album=album,
            lyrics_source="sidecar_lrc",
        )


def _read_metadata(audio_path: Path) -> tuple[str, str, str | None]:
    """Read artist, title, album from audio tags. Fall back to filename parsing."""
    try:
        tags = mutagen.File(audio_path, easy=True)
    except Exception:  # noqa: BLE001
        tags = None

    tag_artist = _first_tag(tags, "artist") if tags else None
    tag_title = _first_tag(tags, "title") if tags else None
    tag_album = _first_tag(tags, "album") if tags else None

    if tag_artist and tag_title:
        return tag_artist, tag_title, tag_album

    # Fallback: parse from filename
    fb_artist, fb_title = _extract_metadata_from_filename(audio_path.stem)
    return tag_artist or fb_artist, tag_title or fb_title, tag_album


def _first_tag(tags: mutagen.FileType, key: str) -> str | None:
    """Get the first value for a tag key, or None."""
    values = tags.get(key)
    if values and len(values) > 0 and values[0].strip():
        return values[0].strip()
    return None


def _extract_metadata_from_filename(stem: str) -> tuple[str, str]:
    """Extract artist and title from filename stem.

    Pattern: '03 - Coldplay - Ghost Story'
    Same logic as the former LrcLyric._extract_metadata.
    """
    parts = re.split(r"\s*-\s*", stem, maxsplit=2)
    if len(parts) >= 3:
        artist, title = parts[1].strip(), parts[2].strip()
    elif len(parts) == 2:
        artist, title = parts[0].strip(), parts[1].strip()
    else:
        artist, title = "Unknown", stem

    title = re.sub(r"\s*\((?:Album Version|Explicit)\)\s*$", "", title)
    return artist, title
