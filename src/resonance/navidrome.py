"""Small Subsonic/OpenSubsonic adapter; credentials stay in POST bodies."""

import hashlib
import json
import math
import secrets
import unicodedata
from collections.abc import Iterator
from dataclasses import replace
from typing import Any
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

import httpx

from resonance.config import NavidromeConfig
from resonance.errors import ApplicationError, NavidromeRejectedError
from resonance.models import ConnectionInfo, Library, LrcLine, ServerPlaylist, Track

MAX_RESPONSE_BYTES = 8_000_000


def source_binding(config: NavidromeConfig) -> dict[str, str]:
    """Index identity can be checked without opening an outbound HTTP client."""
    if not config.base_url or not config.user_id:
        msg = "Configure the Navidrome source before using its index"
        raise ApplicationError(msg, code="not_configured", status=503)
    value = f"{config.base_url.rstrip('/')}\0{config.user_id}"
    return {"source_id": config.server_id, "server_fingerprint": hashlib.sha256(value.encode()).hexdigest()}


def _protocol_error() -> ApplicationError:
    return ApplicationError("Invalid Navidrome response", code="navidrome_protocol", status=502)


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise _protocol_error()
    return float(value)


def _identifier(value: object) -> str:
    if isinstance(value, bool) or not isinstance(value, str | int) or not str(value).strip():
        raise _protocol_error()
    return str(value)


def _rows(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
        raise _protocol_error()
    return value


class NavidromeClient:
    """Reusable synchronous client; a supplied HTTP client remains caller-owned."""

    def __init__(self, config: NavidromeConfig, http: httpx.Client | None = None) -> None:
        if not config.base_url or not config.user_id or not config.user_password or not config.server_id.strip():
            msg = "Configure the Navidrome address, username, password, and server ID"
            raise ApplicationError(msg, code="not_configured", status=503)
        parts = urlsplit(config.base_url)
        if (
            parts.scheme not in {"http", "https"}
            or not parts.hostname
            or any((parts.username, parts.password, parts.query, parts.fragment))
            or (parts.scheme == "http" and not config.allow_http)
        ):
            msg = "Navidrome requires HTTPS; trusted local HTTP must be explicitly enabled"
            raise ApplicationError(msg, code="invalid_configuration", status=503)
        self.config = config
        self.base_url = config.base_url.rstrip("/")
        self._owns_http = http is None
        self._http = http or httpx.Client(timeout=config.timeout, follow_redirects=False)

    def close(self) -> None:
        if self._owns_http:
            self._http.close()

    @property
    def binding(self) -> dict[str, str]:
        """Stable operator scope plus a non-secret endpoint/account fingerprint."""
        return source_binding(self.config)

    def request(self, endpoint: str, params: dict[str, Any] | None = None, *, xml: bool = False) -> dict[str, Any]:
        """Call a fixed API endpoint without returning raw upstream failures."""
        salt = secrets.token_hex(16)
        password = self.config.user_password.get_secret_value() if self.config.user_password else ""
        # This digest is mandated by Subsonic, not a password-storage algorithm.
        token = hashlib.md5((password + salt).encode(), usedforsecurity=False).hexdigest()
        data = {
            **(params or {}),
            "u": self.config.user_id,
            "t": token,
            "s": salt,
            "v": "1.16.1",
            "c": "resonance",
            "f": "xml" if xml else "json",
        }
        try:
            response = self._http.post(f"{self.base_url}/rest/{endpoint}.view", data=data, follow_redirects=False)
            if response.status_code != 200 or len(response.content) > MAX_RESPONSE_BYTES:
                msg = "Navidrome HTTP request failed"
                raise ApplicationError(msg, code="navidrome_unavailable", status=502)
            if xml:
                envelope = self._xml_response(response.content)
            else:
                body = response.json()
                envelope = body.get("subsonic-response") if isinstance(body, dict) else None
            if not isinstance(envelope, dict):
                raise _protocol_error()
            if envelope.get("status") == "failed":
                error = envelope.get("error", {})
                raise NavidromeRejectedError(int(error.get("code", 0)))
            if envelope.get("status") != "ok":
                raise _protocol_error()
        except httpx.HTTPError, ValueError, TypeError, AttributeError, ET.ParseError:
            msg = "Navidrome request failed"
            raise ApplicationError(msg, code="navidrome_unavailable", status=502) from None
        return envelope

    @staticmethod
    def _xml_response(content: bytes) -> dict[str, Any]:
        text = content.decode("utf-8")
        if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
            raise _protocol_error()
        root = ET.fromstring(text)  # noqa: S314 -- declarations rejected above; authenticated peer
        result: dict[str, Any] = dict(root.attrib)
        error = root.find("{*}error")
        if error is not None:
            result["error"] = dict(error.attrib)
        playlist = root.find("{*}playlist")
        if playlist is not None:
            item: dict[str, Any] = dict(playlist.attrib)
            if "public" in item:
                item["public"] = {"true": True, "false": False}.get(item["public"])
            item["song_ids"] = [entry.get("id") for entry in playlist.findall("{*}entry")]
            result["playlist"] = item
        return result

    def inspect(self) -> ConnectionInfo:
        ping = self.request("ping")
        rows = _rows(self.request("getOpenSubsonicExtensions").get("openSubsonicExtensions", []))
        return ConnectionInfo(
            server_type=str(ping.get("type", "")),
            server_version=str(ping.get("serverVersion", "")),
            protocol_version=str(ping.get("version", "")),
            extensions={str(row["name"]): row.get("versions", []) for row in rows if "name" in row},
        )

    def libraries(self) -> list[Library]:
        container = self.request("getMusicFolders").get("musicFolders", {})
        if not isinstance(container, dict):
            raise _protocol_error()
        return [
            Library(_identifier(row.get("id")), str(row.get("name", "")))
            for row in _rows(container.get("musicFolder", []))
        ]

    def tracks(self, library_id: str) -> Iterator[Track]:
        if library_id not in {library.id for library in self.libraries()}:
            msg = "Library is not accessible"
            raise ApplicationError(msg, code="library_unavailable", status=422)
        seen: set[str] = set()
        for page in range(self.config.max_pages):
            data = self.request(
                "search3",
                {
                    "query": "",
                    "musicFolderId": library_id,
                    "artistCount": 0,
                    "albumCount": 0,
                    "songCount": self.config.page_size,
                    "songOffset": page * self.config.page_size,
                },
            ).get("searchResult3", {})
            if not isinstance(data, dict):
                raise _protocol_error()
            rows = _rows(data.get("song", []))
            if not rows:
                return
            for row in rows:
                track = self._track(row, library_id)
                if track.song_id in seen:
                    msg = "Navidrome pagination repeated a song ID"
                    raise ApplicationError(msg, code="inconsistent_paging", status=502)
                seen.add(track.song_id)
                yield track
        msg = "Navidrome listing exceeded its page limit"
        raise ApplicationError(msg, code="listing_limit", status=502)

    def _track(self, data: dict[str, Any], library_id: str) -> Track:
        title = data.get("title")
        if not isinstance(title, str) or not title.strip():
            raise _protocol_error()
        artist = data.get("artist", "Unknown")
        album = data.get("album")
        if not isinstance(artist, str) or (album is not None and not isinstance(album, str)):
            raise _protocol_error()
        return Track(self.config.server_id, library_id, _identifier(data.get("id")), artist, title, album)

    def get_track(self, song_id: str, library_id: str) -> Track:
        data = self.request("getSong", {"id": song_id}).get("song")
        if not isinstance(data, dict) or data.get("id") != song_id:
            raise _protocol_error()
        return self._track(data, library_id)

    def lyrics(self, track: Track) -> Track:
        data = self.request("getLyricsBySongId", {"id": track.song_id}).get("lyricsList", {})
        if not isinstance(data, dict):
            raise _protocol_error()
        variants = _rows(data.get("structuredLyrics", []))
        synced = [row for row in variants if row.get("synced") is True and row.get("kind", "main") == "main"]
        if not synced:
            return replace(track, lyrics_status="unsynced" if variants else "missing")
        preferred = self.config.lyrics_language
        if preferred:
            exact = [row for row in synced if row.get("lang") == preferred]
            unknown = [row for row in synced if row.get("lang", "und") in {"und", "xxx"}]
            synced = exact or unknown
            if not synced:
                return replace(track, lyrics_status="language_unavailable")
        selected = min(synced, key=lambda row: (str(row.get("lang", "und")), json.dumps(row, sort_keys=True)))
        offset = _number(selected.get("offset", 0))
        lines: list[LrcLine] = []
        previous = -math.inf
        for line in _rows(selected.get("line", [])):
            timestamp = (_number(line.get("start")) - offset) / 1000
            value = line.get("value")
            if not isinstance(value, str) or timestamp < previous:
                raise _protocol_error()
            value = unicodedata.normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n"))
            lines.append(LrcLine(timestamp, value))
            previous = timestamp
        return replace(
            track,
            lines=lines,
            lyrics_status="synced" if any(line.text.strip() for line in lines) else "empty",
            language=str(selected.get("lang", "und")),
            offset_ms=offset,
        )

    @staticmethod
    def _playlist(data: dict[str, Any] | None) -> ServerPlaylist:
        if not isinstance(data, dict):
            raise _protocol_error()
        try:
            count = int(data.get("songCount", -1))
        except ValueError, TypeError:
            raise _protocol_error() from None
        return ServerPlaylist(
            id=_identifier(data.get("id")),
            name=str(data.get("name", "")),
            owner=str(data.get("owner", "")),
            public=data.get("public"),
            song_count=count,
            song_ids=data.get("song_ids", []),
        )

    def get_playlist(self, playlist_id: str) -> ServerPlaylist:
        return self._playlist(self.request("getPlaylist", {"id": playlist_id}, xml=True).get("playlist"))

    def create_playlist(self, name: str, song_ids: list[str]) -> str:
        data = self.request("createPlaylist", {"name": name, "songId": song_ids}, xml=True).get("playlist")
        if not isinstance(data, dict):
            raise _protocol_error()
        return _identifier(data.get("id"))

    def playlist_names(self) -> set[str]:
        container = self.request("getPlaylists").get("playlists", {})
        if not isinstance(container, dict):
            raise _protocol_error()
        return {str(row.get("name", "")) for row in _rows(container.get("playlist", []))}
