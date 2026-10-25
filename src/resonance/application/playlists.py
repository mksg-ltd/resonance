"""Create-only private saves from an approved, ordered selection."""

import re
from dataclasses import dataclass

from resonance.errors import ApplicationError, NavidromeRejectedError, external_errors, fail
from resonance.navidrome import NavidromeClient
from resonance.state import SaveJournal, SaveOperation


@dataclass
class PlaylistSelection:
    operation_id: str
    library_id: str
    name: str
    song_ids: list[str]
    allow_duplicate_name: bool = False

    def validate(self) -> None:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", self.operation_id):
            fail("Operation key must be 1-128 letters, digits, dots, colons, underscores or hyphens")
        if not self.library_id.strip() or not self.name.strip() or len(self.name) > 200:
            fail("A library and playlist name (up to 200 characters) are required")
        if any(ord(char) < 32 for char in self.name):
            fail("Playlist names cannot contain control characters")
        if not 1 <= len(self.song_ids) <= 100 or any(not item.strip() or len(item) > 256 for item in self.song_ids):
            fail("Select 1-100 song IDs")
        if len(set(self.song_ids)) != len(self.song_ids):
            fail("Duplicate song IDs are not allowed")

    @property
    def payload(self) -> dict:
        return {
            "v": 1,
            "library_id": self.library_id,
            "name": self.name,
            "song_ids": self.song_ids,
            "private": True,
            "allow_duplicate_name": self.allow_duplicate_name,
        }


def caller_binding(source: NavidromeClient, library_id: str, caller: str) -> dict[str, str]:
    if caller != "operator":
        fail("Caller cannot save playlists", code="forbidden", status=403)
    return {**source.binding, "library_id": library_id, "caller": caller}


def _gate(source: NavidromeClient) -> None:
    info = source.inspect()
    if (
        info.server_type.lower() != "navidrome"
        or info.server_version not in {"0.64.2", "0.64.2 (10114574)"}
        or 1 not in info.extensions.get("formPost", [])
    ):
        fail(
            "Private creation is validated only for Navidrome 0.64.2 with formPost v1",
            code="unsupported_server",
            status=409,
        )


def validate_selection(source: NavidromeClient, selection: PlaylistSelection) -> None:
    """Re-enumerate scoped membership, then revalidate each exact song ID."""
    selection.validate()
    required = set(selection.song_ids)
    found = {track.song_id for track in source.tracks(selection.library_id) if track.song_id in required}
    if found != required:
        fail("Some selected songs are no longer accessible in this library", code="stale_selection", status=422)
    for song_id in selection.song_ids:
        track = source.get_track(song_id, selection.library_id)
        if (
            track.song_id != song_id
            or track.source_id != source.config.server_id
            or track.library_id != selection.library_id
        ):
            fail("Selected song scope changed", code="stale_selection", status=422)
    if not selection.allow_duplicate_name and selection.name in source.playlist_names():
        fail("Playlist name already exists; explicitly acknowledge a duplicate name", code="duplicate_name", status=409)


def _reconcile(source: NavidromeClient, journal: SaveJournal, operation: SaveOperation) -> SaveOperation:
    if operation.playlist_id is None or operation.status == "verified":
        return operation
    try:
        playlist = source.get_playlist(operation.playlist_id)
        expected = operation.request
        matches = (
            playlist.id == operation.playlist_id
            and playlist.owner == source.config.user_id
            and playlist.name == expected["name"]
            and playlist.public is False
            and playlist.song_count == len(expected["song_ids"])
            and playlist.song_ids == expected["song_ids"]
        )
        journal.outcome(
            operation.operation_id, "verified" if matches else "unresolved", None if matches else "readback_mismatch"
        )
    except ApplicationError:
        journal.outcome(operation.operation_id, "unresolved", "readback_unavailable")
    return journal.get(operation.operation_id, operation.binding)


@external_errors("Playlist save interrupted; inspect the same operation key before retrying")
def create_playlist(
    source: NavidromeClient, journal: SaveJournal, selection: PlaylistSelection, *, caller: str = "operator"
) -> SaveOperation:
    selection.validate()
    binding = caller_binding(source, selection.library_id, caller)
    operation = journal.prepare(selection.operation_id, binding, selection.payload)
    if operation.status != "prepared":
        return _reconcile(source, journal, operation)
    _gate(source)
    validate_selection(source, selection)
    if not journal.claim(selection.operation_id):
        return _reconcile(source, journal, journal.get(selection.operation_id, binding))
    try:
        playlist_id = source.create_playlist(selection.name, selection.song_ids)
    except NavidromeRejectedError:
        journal.outcome(selection.operation_id, "failed", "server_rejected")
    except ApplicationError:
        journal.outcome(selection.operation_id, "unresolved", "create_outcome_unknown")
    else:
        # Persist the exact returned ID before any readback; a crash cannot trigger a fresh create.
        journal.record_id(selection.operation_id, playlist_id)
    return _reconcile(source, journal, journal.get(selection.operation_id, binding))


@external_errors("Playlist status is unavailable")
def get_operation(
    source: NavidromeClient, journal: SaveJournal, operation_id: str, library_id: str, *, caller: str = "operator"
) -> SaveOperation:
    return _reconcile(source, journal, journal.get(operation_id, caller_binding(source, library_id, caller)))
