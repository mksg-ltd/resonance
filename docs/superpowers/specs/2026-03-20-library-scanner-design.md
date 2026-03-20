# Library Scanner & Provider Abstraction

**Date:** 2026-03-20
**Status:** Draft
**Supersedes:** PRD-04 (Jellyfin Plugin Architecture Research)

---

## Context

resonance is a semantic search engine for song lyrics. Users search by mood or meaning, and resonance returns matching songs via cosine similarity on embeddings stored in Qdrant.

The original plan was to build a Jellyfin plugin for playlist creation. That approach was abandoned because Jellyfin's playlist/permission model is broken for this use case and would tightly couple resonance to one media server.

**New direction:** resonance outputs m3u playlist files to a shared directory. Any media server (Jellyfin, Navidrome, or anything else) that mounts that directory picks up the playlists automatically. This makes resonance server-agnostic.

To support m3u generation, resonance needs to know the audio file path for each song — not just the lyrics. This requires refactoring the ingest pipeline from "scan for LRC files" to "scan for audio files and find their lyrics."

## Goals

- Decouple song/lyrics discovery from the ingest pipeline
- Make the audio file the primary unit (not the LRC file)
- Extract richer metadata from audio tags (artist, title, album) instead of filename parsing
- Store audio file paths in Qdrant so downstream consumers (m3u generation) can use them
- Support embedded lyrics extraction (MP3, FLAC, AAC) alongside existing sidecar LRC files

## Non-Goals

- m3u playlist generation (separate spec, consumes this work)
- Unsynced lyrics / section-tag-based chunking (`[Chorus]`, `[Bridge]`) — future work
- Jellyfin or Subsonic API integration
- Backward compatibility with existing Qdrant collections (will be recreated)

## Design

### SongData Model

Added to `models.py`. This is what the scanner yields and what the ingest pipeline consumes.

```python
@dataclass
class SongData:
    artist: str
    title: str
    audio_path: Path
    filename: str
    lyrics_text: str
    lines: list[LrcLine]
    album: str | None = None
```

- `audio_path`: absolute path to the audio file on disk
- `filename`: audio filename, set by scanner, stored in Qdrant payload
- `lines`: timestamped `LrcLine` list — only synced lyrics are supported in this phase
- `album`: from audio tags when available, None otherwise

### LibraryScanner

New module: `src/resonance/scanner.py`

```
LibraryScanner
├── scan(path: Path) -> Iterator[SongData]
│     walks path recursively for SUPPORTED_EXTENSIONS
│     for each audio file:
│       1. try extract_embedded(audio_path) -> SongData or None
│       2. if None, try extract_sidecar_lrc(audio_path) -> SongData or None
│       3. if None, log and continue
│
├── extract_embedded(audio_path) -> SongData | None
│     uses mutagen to open the file
│     dispatches by tag type:
│       ID3 (mp3)      -> SYLT tag (synced lyrics), parse to LrcLines
│       Vorbis (flac)   -> LYRICS field, check if timestamped
│       MP4 (m4a/aac)   -> ©lyr, check if timestamped
│     extracts artist/title/album from tags
│     returns None if no synced lyrics found
│
├── extract_sidecar_lrc(audio_path) -> SongData | None
│     looks for .lrc file with same stem in same directory
│     uses existing parser.py to parse timestamped lines
│     extracts artist/title/album from audio tags (mutagen)
│     filename parsing as last-resort fallback for metadata
│     returns None if no .lrc found
│
└── SUPPORTED_EXTENSIONS = {".mp3", ".flac", ".m4a", ".ogg", ".opus"}
```

**Metadata source priority:** Always prefer audio file tags over filename parsing. mutagen reads tags from any supported format. Filename parsing (`03 - Coldplay - Ghost Story.flac`) is the fallback only when tags are missing.

**Embedded lyrics — tag formats the implementer must handle:**

| Tag System        | Formats         | Synced Lyrics Field                             | Metadata Fields                                 |
| ----------------- | --------------- | ----------------------------------------------- | ----------------------------------------------- |
| ID3v2 (v2.3/v2.4) | MP3             | `SYLT` (synchronized lyrics)                    | `TPE1` (artist), `TIT2` (title), `TALB` (album) |
| Vorbis Comments   | FLAC, OGG, Opus | `LYRICS` field — check for LRC-style timestamps | `ARTIST`, `TITLE`, `ALBUM`                      |
| MP4/iTunes atoms  | AAC (m4a), ALAC | `©lyr` — check for LRC-style timestamps         | `©ART` (artist), `©nam` (title), `©alb` (album) |

The implementer should consult the mutagen documentation and the relevant tag specs (ID3v2.4, Vorbis Comments, MP4 atoms) for parsing details. Key things to verify during implementation:

- `SYLT` frames have a content type field — only `LYRICS` type is relevant (not karaoke, etc.)
- Vorbis and MP4 lyrics fields may contain plain text (unsynced) or LRC-formatted text (synced). Parse the content to determine which.
- ID3v2 may have multiple `USLT`/`SYLT` frames for different languages. Pick the first or the one matching a configured language preference.

**Extraction order is not configurable.** Embedded first, sidecar second. This is the correct priority — embedded lyrics are authoritative, sidecar is supplementary.

**Logging:**

| Level   | Message                                                  |
| ------- | -------------------------------------------------------- |
| INFO    | `Scanning {path}, found {n} audio files`                 |
| DEBUG   | `Embedded synced lyrics: {filename}`                     |
| DEBUG   | `Sidecar LRC found: {filename}`                          |
| WARNING | `No synced lyrics (unsynced only, skipping): {filename}` |
| DEBUG   | `No lyrics found, skipping: {filename}`                  |

### Qdrant Payload

Per-chunk payload stored in Qdrant:

```python
{
    "artist": "Coldplay",
    "title": "Ghost Story",
    "album": "Ghost Stories",
    "filename": "03 - Coldplay - Ghost Story.flac",
    "audio_path": "Coldplay/Ghost Stories/03 - Coldplay - Ghost Story.flac",
    "lyrics_source": "sidecar_lrc",
    "section": "verse_1",
    "position": 0,
    "total_sections": 4,
    "lyrics": "...",
    "start_sec": 12.5,
    "duration_sec": 45.0,
}
```

- `filename`: audio file name (not LRC)
- `audio_path`: path relative to the collection's `data_dir` — portable across Docker mount points, used by future m3u generation
- `lyrics_source`: `"embedded"` or `"sidecar_lrc"` — for debugging/observability
- `album`: from tags, nullable

Collection metadata point (id=0) is unchanged — still stores provider/model/dimensions.

### Ingest Pipeline Changes

**Current flow:**

```
run_ingest(data_dir) -> rglob("*.lrc") -> chunk_song(path) -> embed -> Qdrant
```

**New flow:**

```
run_ingest(data_dir) -> LibraryScanner.scan(data_dir) -> chunk_song_data(SongData) -> embed -> Qdrant
```

Changes to `run_ingest`:

1. Replace `source_dir.rglob("*.lrc")` + `chunk_song()` with `LibraryScanner().scan(source_dir)`
2. Scanner yields `SongData` (already parsed, metadata from tags)
3. New `chunk_song_data(song_data)` in `chunker.py` — takes `SongData`, uses `.lines` to chunk (same chunking logic as today)
4. Build Qdrant payload from `SongData` + chunk fields, including `audio_path` as `str(song.audio_path.relative_to(source_dir))`

**What doesn't change:**

- Embedding and Qdrant upsert logic
- Collection creation / metadata point (id=0)
- Batch size, force/skip logic
- API contracts (`IngestRequest` / `IngestResponse`)
- Search endpoint — reads from Qdrant payload, just has more fields available

**What gets removed:**

- `LrcLyric.from_file()` and `LrcLyric._extract_metadata()` — scanner handles discovery and metadata
- `MUSIC_DIR` hardcoded constant — already passed as `data_dir`

### File Layout

```
src/resonance/
├── scanner.py          # NEW — LibraryScanner, extract_embedded, extract_sidecar_lrc
├── models.py           # SongData added alongside existing LrcLine, LrcChunk
├── chunker.py          # chunk_song_data(SongData) replaces chunk_song(Path)
├── parser.py           # unchanged — still parses LRC content into LrcLines
├── routes/ingest.py    # run_ingest uses LibraryScanner
└── ...
```

### Dependencies

- `mutagen` — added to project dependencies for audio tag reading

## m3u Context (Not In Scope)

For the separate m3u spec: both Jellyfin and Navidrome auto-discover m3u files during library scans. Both resolve relative paths relative to the m3u file's location. The only Docker-compatible approach is relative paths — never absolute paths.

The `audio_path` field stored in Qdrant (relative to `data_dir`) is what the m3u generator will use. A `Playlists/` subdirectory within the music mount is the intended output location. The m3u generator computes relative paths from the playlist file to each audio file.

This is captured here for context. Design and implementation are a separate spec.
