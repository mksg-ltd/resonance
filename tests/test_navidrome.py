"""Protocol and normalized-data tests with a real HTTP client and fake server."""

import json
from dataclasses import asdict
from urllib.parse import parse_qs

import httpx
import pytest

from resonance.application.library import get_lyrics, list_tracks
from resonance.config import NavidromeConfig
from resonance.errors import ApplicationError, NavidromeRejectedError
from resonance.models import Track
from resonance.navidrome import NavidromeClient


def settings(**kwargs):
    return NavidromeConfig(
        base_url="https://music.test", user_id="operator", user_password="test-secret", _env_file=None, **kwargs
    )


def ok(**payload):
    return httpx.Response(200, json={"subsonic-response": {"status": "ok", **payload}})


def client_for(handler, **kwargs):
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return NavidromeClient(settings(**kwargs), http)


def test_paged_tracks_have_server_identity_without_filesystem_paths():
    offsets = []

    def server(request):
        assert request.method == "POST"
        assert not request.url.query
        form = parse_qs(request.content.decode(), keep_blank_values=True)
        assert form["u"] == ["operator"]
        assert "p" not in form
        assert len(form["t"][0]) == 32
        if request.url.path.endswith("getMusicFolders.view"):
            return ok(musicFolders={"musicFolder": [{"id": 2, "name": "English"}]})
        assert form["musicFolderId"] == ["2"]
        offset = int(form["songOffset"][0])
        offsets.append(offset)
        songs = (
            [{"id": f"song-{offset}", "artist": "An Artist", "title": "A Recording", "album": "One"}]
            if offset < 2
            else []
        )
        return ok(searchResult3={"song": songs})

    client = client_for(server, page_size=1)
    tracks = list(client.tracks("2"))
    assert offsets == [0, 1, 2]
    assert [track.song_id for track in tracks] == ["song-0", "song-1"]
    assert tracks[0].source_id == "home" and tracks[0].library_id == "2"
    assert "audio_path" not in asdict(tracks[0])
    assert "filename" not in asdict(tracks[0])


def test_paging_duplicate_and_unknown_library_are_explicit_failures():
    def server(request):
        if request.url.path.endswith("getMusicFolders.view"):
            return ok(musicFolders={"musicFolder": [{"id": 2, "name": "English"}]})
        return ok(searchResult3={"song": [{"id": "same", "title": "Same"}]})

    client = client_for(server, page_size=1)
    with pytest.raises(ApplicationError, match="repeated"):
        list(client.tracks("2"))
    with pytest.raises(ApplicationError, match="not accessible"):
        list(client.tracks("99"))


def test_page_resource_cap_does_not_claim_complete_listing():
    def server(request):
        if request.url.path.endswith("getMusicFolders.view"):
            return ok(musicFolders={"musicFolder": [{"id": 2, "name": "English"}]})
        return ok(searchResult3={"song": [{"id": "one", "title": "One"}]})

    with pytest.raises(ApplicationError, match="page limit"):
        list(client_for(server, max_pages=1).tracks("2"))


def test_structured_lyrics_select_language_and_subtract_positive_offset():
    variants = [
        {"lang": "eng", "synced": False, "line": [{"value": "plain words"}]},
        {"lang": "tam", "synced": True, "line": [{"start": 0, "value": "other version"}]},
        {
            "lang": "eng",
            "synced": True,
            "offset": 100,
            "line": [
                {"start": 0, "value": "[Verse] Paper stars"},
                {"start": 1000, "value": "Drift across my window"},
            ],
        },
    ]
    client = client_for(lambda _: ok(lyricsList={"structuredLyrics": variants}), lyrics_language="eng")
    result = client.lyrics(Track("home", "2", "one", "Artist", "Song"))
    assert result.language == "eng" and result.lyrics_status == "synced"
    assert [line.timestamp_sec for line in result.lines] == [-0.1, 0.9]
    assert result.lines[0].text == "[Verse] Paper stars"


@pytest.mark.parametrize("variants,status", [([], "missing"), ([{"synced": False, "line": []}], "unsynced")])
def test_no_synthetic_timestamps_for_missing_or_unsynced_lyrics(variants, status):
    result = client_for(lambda _: ok(lyricsList={"structuredLyrics": variants})).lyrics(
        Track("home", "2", "one", "Artist", "Song")
    )
    assert result.lyrics_status == status
    assert result.lines == []


def test_unknown_language_is_explicit_fallback_and_malformed_timing_fails():
    variants = [{"synced": True, "lang": "xxx", "line": [{"start": 500, "value": "A paper kite"}]}]
    client = client_for(lambda _: ok(lyricsList={"structuredLyrics": variants}), lyrics_language="eng")
    track = Track("home", "2", "one", "Artist", "Song")
    assert client.lyrics(track).language == "xxx"
    del variants[0]["line"][0]["start"]
    with pytest.raises(ApplicationError, match="Invalid Navidrome"):
        client.lyrics(track)


def test_failed_envelopes_and_transport_errors_do_not_expose_credentials():
    rejected = client_for(
        lambda _: httpx.Response(
            200, json={"subsonic-response": {"status": "failed", "error": {"code": 40, "message": "test-secret"}}}
        )
    )
    with pytest.raises(NavidromeRejectedError) as caught:
        rejected.inspect()
    assert caught.value.error_code == 40
    assert "test-secret" not in str(caught.value)

    def timeout(request):
        raise httpx.ReadTimeout("test-secret", request=request)

    with pytest.raises(ApplicationError) as caught:
        client_for(timeout).inspect()
    assert "test-secret" not in str(caught.value)


def test_http_requires_explicit_trust_and_redirects_are_not_followed():
    with pytest.raises(ApplicationError, match="HTTPS"):
        NavidromeClient(
            NavidromeConfig(base_url="http://music.test", user_id="user", user_password="secret", _env_file=None)
        )
    trusted = NavidromeConfig(
        base_url="http://music.test", user_id="user", user_password="secret", allow_http=True, _env_file=None
    )
    calls = []

    def redirect(request):
        calls.append(request)
        return httpx.Response(302, headers={"Location": "https://other.test"})

    with httpx.Client(transport=httpx.MockTransport(redirect), follow_redirects=True) as http:
        with pytest.raises(ApplicationError):
            NavidromeClient(trusted, http).inspect()
    assert len(calls) == 1


def test_xml_false_visibility_is_explicit_and_entities_are_rejected():
    xml = b'<subsonic-response status="ok"><playlist id="p" owner="operator" name="test" public="false" songCount="2"><entry id="b"/><entry id="a"/></playlist></subsonic-response>'
    snapshot = client_for(lambda _: httpx.Response(200, content=xml)).get_playlist("p")
    assert snapshot.public is False
    assert snapshot.song_ids == ["b", "a"]
    poisoned = b'<!DOCTYPE x [<!ENTITY data "words">]><subsonic-response status="ok"/>'
    with pytest.raises(ApplicationError):
        client_for(lambda _: httpx.Response(200, content=poisoned)).get_playlist("p")


def test_read_only_application_and_cli_only_use_read_endpoints(monkeypatch, capsys):
    from resonance import library

    endpoints = []

    def server(request):
        endpoints.append(request.url.path)
        if request.url.path.endswith("getMusicFolders.view"):
            return ok(musicFolders={"musicFolder": [{"id": 2, "name": "English"}]})
        if request.url.path.endswith("search3.view"):
            offset = parse_qs(request.content.decode(), keep_blank_values=True)["songOffset"][0]
            return ok(searchResult3={"song": [{"id": "one", "title": "One"}] if offset == "0" else []})
        return ok(lyricsList={"structuredLyrics": []})

    client = client_for(server)
    assert len(list_tracks(client, "2", 1)) == 1
    assert get_lyrics(client, "2", "one").lyrics_status == "missing"
    monkeypatch.setattr(library, "NavidromeClient", lambda _: client)
    monkeypatch.setattr("sys.argv", ["resonance-library", "tracks", "--library", "2", "--limit", "1"])
    library.main()
    assert json.loads(capsys.readouterr().out)[0]["song_id"] == "one"
    assert all("Playlist" not in endpoint for endpoint in endpoints)
