"""Small Subsonic/OpenSubsonic adapter; credentials stay in POST bodies."""

import hashlib
import json
import logging
import math
import secrets
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from typing import Any, NoReturn
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

import httpx

from resonance.config import NavidromeConfig
from resonance.errors import ApplicationError, NavidromeRejectedError
from resonance.models import ConnectionInfo, Library, LrcLine, ServerPlaylist, Track

MAX_RESPONSE_BYTES = 8_000_000
logger = logging.getLogger("uvicorn.error.resonance.navidrome")


@dataclass(frozen=True)
class NavidromeCredentials:
    """Credentials supplied by the authenticated caller, never global settings."""

    username: str
    password: str = field(repr=False)


def canonical_server_url(value: str) -> str:
    """Normalize the configured Navidrome endpoint for a stable server fingerprint."""
    try:
        parts = urlsplit(value.strip())
        port = parts.port
    except ValueError as error:
        msg = "Invalid Navidrome server URL"
        raise ApplicationError(msg, code="invalid_configuration", status=503) from error
    if (
        parts.scheme.lower() not in {"http", "https"}
        or not parts.hostname
        or any((parts.username, parts.password, parts.query, parts.fragment))
    ):
        msg = "Invalid Navidrome server URL"
        raise ApplicationError(msg, code="invalid_configuration", status=503)
    scheme = parts.scheme.lower()
    host = parts.hostname.lower()
    if port is not None and not ((scheme == "https" and port == 443) or (scheme == "http" and port == 80)):
        host = f"[{host}]:{port}" if ":" in host else f"{host}:{port}"
    elif ":" in host:
        host = f"[{host}]"
    path = "/" + parts.path.strip("/") if parts.path.strip("/") else ""
    return f"{scheme}://{host}{path}"


def source_binding(config: NavidromeConfig) -> dict[str, str]:
    """Index identity can be checked without opening an outbound HTTP client."""
    if not config.base_url or not config.server_id.strip():
        msg = "Configure the Navidrome source before using its index"
        raise ApplicationError(msg, code="not_configured", status=503)
    value = canonical_server_url(config.base_url)
    return {"source_id": config.server_id, "server_fingerprint": hashlib.sha256(value.encode()).hexdigest()}


def legacy_source_fingerprint(base_url: str, username: str) -> str:
    """Reproduce the pre-auth source fingerprint for proof-gated migrations."""
    return hashlib.sha256(f"{base_url.rstrip('/')}\0{username}".encode()).hexdigest()


def _protocol_error(diagnostic: str = "unexpected_response_shape") -> ApplicationError:
    return ApplicationError("Invalid Navidrome response", code="navidrome_protocol", status=502, diagnostic=diagnostic)


def _raise_protocol_error(diagnostic: str = "unexpected_response_shape") -> NoReturn:
    error = _protocol_error(diagnostic)
    raise error


def _number(value: object, field: str = "number") -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        _raise_protocol_error(f"{field}:expected_finite_number")
    return float(value)


def _identifier(value: object, field: str = "identifier") -> str:
    if isinstance(value, bool) or not isinstance(value, str | int) or not str(value).strip():
        _raise_protocol_error(f"{field}:expected_nonempty_identifier")
    return str(value)


def _rows(value: object, field: str = "response") -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
        _raise_protocol_error(f"{field}:expected_list_of_objects")
    return value


class NavidromeClient:
    """Reusable user-scoped client; a supplied HTTP client remains caller-owned."""

    def __init__(
        self,
        config: NavidromeConfig,
        credentials: NavidromeCredentials,
        http: httpx.Client | None = None,
    ) -> None:
        if (
            not config.base_url
            or not config.server_id.strip()
            or not credentials.username.strip()
            or not credentials.password
        ):
            msg = "Configure the Navidrome address and provide user credentials"
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
        self.credentials = credentials
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
        password = self.credentials.password
        # This digest is mandated by Subsonic, not a password-storage algorithm.
        token = hashlib.md5((password + salt).encode(), usedforsecurity=False).hexdigest()
        data = {
            **(params or {}),
            "u": self.credentials.username,
            "t": token,
            "s": salt,
            "v": "1.16.1",
            "c": "resonance",
            "f": "xml" if xml else "json",
        }
        try:
            response = self._http.post(f"{self.base_url}/rest/{endpoint}.view", data=data, follow_redirects=False)
            if response.status_code != 200 or len(response.content) > MAX_RESPONSE_BYTES:
                logger.warning(
                    "Navidrome HTTP request failed: endpoint=%s status=%d response_bytes=%d",
                    endpoint,
                    response.status_code,
                    len(response.content),
                )
                msg = "Navidrome HTTP request failed"
                raise ApplicationError(msg, code="navidrome_unavailable", status=502)  # noqa: TRY301
            body: object | None = None
            if xml:
                envelope = self._xml_response(response.content)
            else:
                body = response.json()
                envelope = body.get("subsonic-response") if isinstance(body, dict) else None
            if not isinstance(envelope, dict):
                if isinstance(body, dict):
                    body_keys = ",".join(sorted(key for key in body if isinstance(key, str))[:8]) or "none"
                    body_shape = f"object_keys:{body_keys}"
                else:
                    body_shape = type(body).__name__ if not xml else "xml"
                _raise_protocol_error(f"{endpoint}:missing_response_envelope:{body_shape}")
            if envelope.get("status") == "failed":
                error = envelope.get("error", {})
                raise NavidromeRejectedError(int(error.get("code", 0)))  # noqa: TRY301
            if envelope.get("status") != "ok":
                status_type = type(envelope.get("status")).__name__
                _raise_protocol_error(f"{endpoint}:unexpected_status_type:{status_type}")
        except NavidromeRejectedError as error:
            logger.warning("Navidrome rejected request: endpoint=%s server_error_code=%d", endpoint, error.error_code)
            raise
        except ApplicationError as error:
            logger.warning(
                "Navidrome request failed: endpoint=%s code=%s diagnostic=%s",
                endpoint,
                error.code,
                error.diagnostic or "none",
            )
            raise
        except (httpx.HTTPError, ValueError, TypeError, AttributeError, ET.ParseError) as error:
            logger.warning("Navidrome request error: endpoint=%s exception_type=%s", endpoint, type(error).__name__)
            msg = "Navidrome request failed"
            raise ApplicationError(msg, code="navidrome_unavailable", status=502) from None
        return envelope

    @staticmethod
    def _xml_response(content: bytes) -> dict[str, Any]:
        text = content.decode("utf-8")
        if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
            _raise_protocol_error("xml_forbidden_declaration")
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
            _raise_protocol_error("music_folders_not_object")
        return [
            Library(_identifier(row.get("id")), str(row.get("name", "")))
            for row in _rows(container.get("musicFolder", []), "musicFolders.musicFolder")
        ]

    def tracks(self, library_id: str) -> Iterator[Track]:
        if library_id not in {library.id for library in self.libraries()}:
            msg = "Library is not accessible"
            raise ApplicationError(msg, code="library_unavailable", status=422)
        seen: set[str] = set()
        for page in range(self.config.max_pages):
            try:
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
                    _raise_protocol_error("search_result_not_object")
                rows = _rows(data.get("song", []), "searchResult3.song")
            except ApplicationError as error:
                logger.warning(
                    "Navidrome track page rejected: endpoint=search3 page=%d offset=%d code=%s diagnostic=%s",
                    page + 1,
                    page * self.config.page_size,
                    error.code,
                    error.diagnostic or "none",
                )
                raise
            if not rows:
                return
            for row_number, row in enumerate(rows, start=1):
                try:
                    track = self._track(row, library_id)
                except ApplicationError as error:
                    logger.warning(
                        "Navidrome track row rejected: endpoint=search3 page=%d row=%d code=%s diagnostic=%s",
                        page + 1,
                        row_number,
                        error.code,
                        error.diagnostic or "none",
                    )
                    raise
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
            _raise_protocol_error("track_title_missing_or_invalid")
        artist = data.get("artist", "Unknown")
        album = data.get("album")
        if not isinstance(artist, str) or (album is not None and not isinstance(album, str)):
            _raise_protocol_error("track_artist_or_album_invalid")
        return Track(
            self.config.server_id,
            library_id,
            _identifier(data.get("id"), "song.id"),
            artist,
            title,
            album,
        )

    def get_track(self, song_id: str, library_id: str) -> Track:
        data = self.request("getSong", {"id": song_id}).get("song")
        if not isinstance(data, dict) or data.get("id") != song_id:
            _raise_protocol_error("get_song_mismatch_or_invalid")
        return self._track(data, library_id)

    def lyrics(self, track: Track) -> Track:
        data = self.request("getLyricsBySongId", {"id": track.song_id}).get("lyricsList", {})
        if not isinstance(data, dict):
            _raise_protocol_error("lyrics_list_not_object")
        variants = _rows(data.get("structuredLyrics", []), "lyricsList.structuredLyrics")
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
        offset = _number(selected.get("offset", 0), "structuredLyrics.offset")
        lines: list[LrcLine] = []
        previous = -math.inf
        for line in _rows(selected.get("line", []), "structuredLyrics.line"):
            timestamp = (_number(line.get("start"), "structuredLyrics.line.start") - offset) / 1000
            value = line.get("value")
            if not isinstance(value, str) or timestamp < previous:
                _raise_protocol_error("lyrics_line_value_invalid_or_timestamps_out_of_order")
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
            _raise_protocol_error()
        try:
            count = int(data.get("songCount", -1))
        except ValueError, TypeError:
            error = _protocol_error()
            raise error from None
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
            _raise_protocol_error()
        return _identifier(data.get("id"))

    def playlist_names(self) -> set[str]:
        container = self.request("getPlaylists").get("playlists", {})
        if not isinstance(container, dict):
            _raise_protocol_error()
        return {str(row.get("name", "")) for row in _rows(container.get("playlist", []))}
