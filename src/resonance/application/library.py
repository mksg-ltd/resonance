"""Read-only library operations shared by transports."""

from itertools import islice

from resonance.errors import ApplicationError
from resonance.models import Track
from resonance.navidrome import NavidromeClient


def list_tracks(client: NavidromeClient, library_id: str, limit: int = 20) -> list[Track]:
    """List a bounded number of metadata records from one visible library."""
    if not 1 <= limit <= 1000:
        msg = "Track limit must be between 1 and 1000"
        raise ApplicationError(msg)
    return list(islice(client.tracks(library_id), limit))


def get_lyrics(client: NavidromeClient, library_id: str, song_id: str) -> Track:
    """Check folder membership before retrieving a recording's lyrics."""
    for track in client.tracks(library_id):
        if track.song_id == song_id:
            return client.lyrics(track)
    msg = "Song does not belong to the selected library"
    raise ApplicationError(msg, code="song_unavailable", status=422)
