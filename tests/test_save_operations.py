"""Real SQLite + production Navidrome transport/application, including concurrency."""

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier
from urllib.parse import parse_qs
from xml.sax.saxutils import quoteattr

import httpx
import pytest

from resonance.application.playlists import PlaylistSelection, caller_binding, create_playlist, get_operation
from resonance.config import NavidromeConfig
from resonance.errors import ApplicationError
from resonance.navidrome import NavidromeClient, NavidromeCredentials, legacy_source_fingerprint
from resonance.state import SaveJournal


class SaveServer:
    def __init__(self):
        self.created = []
        self.calls = []
        self.version = "0.64.2 (10114574)"
        self.create_mode = "ok"
        self.read_mode = "ok"
        self.overrides = {}
        self.members = ["one", "two", "three"]
        self.names = []
        self.owner = "operator"
        self.stale = None
        self.before_create = None

    @staticmethod
    def ok(**kwargs):
        return httpx.Response(200, json={"subsonic-response": {"status": "ok", **kwargs}})

    def __call__(self, request):
        endpoint = request.url.path.rsplit("/", 1)[1].removesuffix(".view")
        form = parse_qs(request.content.decode(), keep_blank_values=True)
        self.calls.append(endpoint)
        if endpoint == "ping":
            return self.ok(type="navidrome", serverVersion=self.version, version="1.16.1")
        if endpoint == "getOpenSubsonicExtensions":
            return self.ok(openSubsonicExtensions=[{"name": "formPost", "versions": [1]}])
        if endpoint == "getMusicFolders":
            user = form["u"][0]
            library = {"id": "3", "name": "Restricted"} if user == "listener" else {"id": "2", "name": "English"}
            return self.ok(musicFolders={"musicFolder": [library]})
        if endpoint == "search3":
            assert form["musicFolderId"][0] in {"2", "3"}
            songs = [{"id": item, "title": "Fixture"} for item in self.members]
            return self.ok(searchResult3={"song": songs if form["songOffset"] == ["0"] else []})
        if endpoint == "getSong":
            if form["id"] == [self.stale]:
                return httpx.Response(200, json={"subsonic-response": {"status": "failed", "error": {"code": 70}}})
            return self.ok(song={"id": form["id"][0], "title": "Fixture"})
        if endpoint == "getPlaylists":
            return self.ok(playlists={"playlist": [{"name": name} for name in self.names]})
        if endpoint == "createPlaylist":
            if self.before_create:
                self.before_create()
            if self.create_mode == "rejected":
                return httpx.Response(
                    200, content='<subsonic-response status="failed"><error code="50"/></subsonic-response>'
                )
            self.created.append({"id": f"p-{len(self.created)}", "name": form["name"][0], "song_ids": form["songId"]})
            if self.create_mode == "timeout":
                raise httpx.ReadTimeout("credential should not leak", request=request)
            if self.create_mode == "no_id":
                return httpx.Response(200, content='<subsonic-response status="ok"><playlist/></subsonic-response>')
            if self.create_mode == "http500":
                return httpx.Response(500)
            if self.create_mode == "crash":
                raise KeyboardInterrupt("simulated process interruption")
            return httpx.Response(
                200,
                content=f'<subsonic-response status="ok"><playlist id="{self.created[-1]["id"]}"/></subsonic-response>',
            )
        if endpoint == "getPlaylist":
            if self.read_mode == "timeout":
                raise httpx.ReadTimeout("private response", request=request)
            playlist = next(item for item in self.created if item["id"] == form["id"][0])
            attributes = {
                "id": playlist["id"],
                "name": playlist["name"],
                "owner": self.owner,
                "public": "false",
                "songCount": str(len(playlist["song_ids"])),
            }
            attributes.update(self.overrides)
            ids = playlist["song_ids"] if self.read_mode != "wrong_order" else list(reversed(playlist["song_ids"]))
            attrs = " ".join(f"{key}={quoteattr(value)}" for key, value in attributes.items() if value is not None)
            entries = "".join(f"<entry id={quoteattr(item)}/>" for item in ids)
            return httpx.Response(
                200,
                content=f'<subsonic-response status="ok"><playlist {attrs}>{entries}</playlist></subsonic-response>',
            )
        raise AssertionError(endpoint)

    def client(self, *, username="operator", **kwargs):
        config = NavidromeConfig(base_url="https://music.test", _env_file=None, **kwargs)
        return NavidromeClient(
            config, NavidromeCredentials(username, "test-secret"), httpx.Client(transport=httpx.MockTransport(self))
        )


def selection(**kwargs):
    return replace(PlaylistSelection("operation-1", "2", "Paper Stars", ["three", "one", "two"]), **kwargs)


def test_verified_ordered_save_persists_and_same_key_restart_never_recreates(tmp_path):
    server, path = SaveServer(), tmp_path / "journal.sqlite3"
    journal, source = SaveJournal(path), server.client()
    result = create_playlist(source, journal, selection())
    assert result.status == "verified" and result.playlist_id == "p-0"
    assert server.created[0]["song_ids"] == ["three", "one", "two"]
    server.calls.clear()
    retried = create_playlist(source, SaveJournal(path), selection())
    assert retried.status == "verified" and not server.calls
    with sqlite3.connect(path) as db:
        row = db.execute("SELECT status,request,binding FROM save_operations").fetchone()
    assert row[0] == "verified" and json.loads(row[1])["private"] is True
    assert "test-secret" not in str(row) and "lyrics" not in str(row)


@pytest.mark.parametrize(
    "change", [dict(name="Changed"), dict(song_ids=["one", "three", "two"]), dict(library_id="other")]
)
def test_global_key_conflicts_on_changed_payload_or_scope(tmp_path, change):
    server, journal = SaveServer(), SaveJournal(tmp_path / "j.sqlite3")
    create_playlist(server.client(), journal, selection())
    with pytest.raises(ApplicationError) as error:
        create_playlist(server.client(), journal, selection(**change))
    assert error.value.code == "operation_conflict" and len(server.created) == 1
    with pytest.raises(ApplicationError):
        create_playlist(server.client(server_id="rebuilt"), journal, selection())
    changed_account = server.client()
    changed_account.credentials = NavidromeCredentials("another-account", "test-secret")
    with pytest.raises(ApplicationError):
        create_playlist(changed_account, journal, selection())


def test_legacy_save_binding_migrates_proven_state_without_losing_operation(tmp_path):
    source = SaveServer().client()
    journal = SaveJournal(tmp_path / "legacy.sqlite3")
    old_binding = {
        **source.binding,
        "server_fingerprint": legacy_source_fingerprint("https://music.test", "operator"),
        "library_id": "2",
        "caller": "operator",
    }
    operation = selection(operation_id="legacy-operation")
    journal.prepare(operation.operation_id, old_binding, operation.payload)
    assert journal.claim(operation.operation_id)
    journal.record_id(operation.operation_id, "saved-playlist")
    journal.outcome(operation.operation_id, "unresolved", "readback_unavailable")

    blocked = journal.migrate_legacy_bindings(source.binding, old_binding["server_fingerprint"], "admin", {"2"})
    migrated_binding = {**source.binding, "library_id": "2", "caller": "admin"}
    migrated = journal.get(operation.operation_id, migrated_binding)

    assert not blocked
    assert migrated.status == "unresolved"
    assert migrated.playlist_id == "saved-playlist"
    assert migrated.request == operation.payload


def test_unproven_unresolved_save_binding_blocks_without_mutation(tmp_path):
    source = SaveServer().client()
    journal = SaveJournal(tmp_path / "unknown-legacy.sqlite3")
    old_binding = {**source.binding, "server_fingerprint": "unknown", "library_id": "2", "caller": "operator"}
    operation = selection(operation_id="legacy-unproven")
    journal.prepare(operation.operation_id, old_binding, operation.payload)
    journal.claim(operation.operation_id)
    before = journal.get(operation.operation_id, old_binding)

    blocked = journal.migrate_legacy_bindings(source.binding, None, "admin", {"2"})
    after = journal.get(operation.operation_id, old_binding)

    assert blocked
    assert after.status == before.status == "submitting"
    assert after.binding == before.binding


@pytest.mark.parametrize("mode", ["timeout", "no_id", "http500"])
def test_unknown_create_outcome_never_retries_create_even_after_restart(tmp_path, mode):
    server, path = SaveServer(), tmp_path / "j.sqlite3"
    server.create_mode = mode
    first = create_playlist(server.client(), SaveJournal(path), selection())
    assert first.status == "unresolved" and first.playlist_id is None
    server.create_mode = "ok"
    second = create_playlist(server.client(), SaveJournal(path), selection())
    assert second.status == "unresolved" and len(server.created) == 1


def test_crash_after_remote_create_keeps_submitting_and_no_duplicate(tmp_path):
    server, path = SaveServer(), tmp_path / "j.sqlite3"
    server.create_mode = "crash"
    with pytest.raises(KeyboardInterrupt):
        create_playlist(server.client(), SaveJournal(path), selection())
    server.create_mode = "ok"
    assert create_playlist(server.client(), SaveJournal(path), selection()).status == "submitting"
    assert len(server.created) == 1


def test_known_id_survives_failed_readback_then_reconciles_without_create(tmp_path):
    server, path = SaveServer(), tmp_path / "j.sqlite3"
    server.read_mode = "timeout"
    first = create_playlist(server.client(), SaveJournal(path), selection())
    assert first.status == "unresolved" and first.playlist_id == "p-0"
    server.read_mode = "ok"
    result = get_operation(server.client(), SaveJournal(path), "operation-1", "2")
    assert result.status == "verified" and len(server.created) == 1


@pytest.mark.parametrize(
    "overrides,mode",
    [
        ({"public": "true"}, "ok"),
        ({"public": None}, "ok"),
        ({"owner": "other"}, "ok"),
        ({"name": "Other"}, "ok"),
        ({"songCount": "99"}, "ok"),
        ({"id": "other-id"}, "ok"),
        ({}, "wrong_order"),
    ],
)
def test_readback_mismatch_is_never_verified_or_repaired(tmp_path, overrides, mode):
    server = SaveServer()
    server.overrides, server.read_mode = overrides, mode
    result = create_playlist(server.client(), SaveJournal(tmp_path / "j.sqlite3"), selection())
    assert result.status == "unresolved" and result.reason == "readback_mismatch"
    assert len(server.created) == 1


def test_definitive_rejection_is_failed_without_duplicate_retry(tmp_path):
    server, journal = SaveServer(), SaveJournal(tmp_path / "j.sqlite3")
    server.create_mode = "rejected"
    assert create_playlist(server.client(), journal, selection()).status == "failed"
    server.create_mode = "ok"
    assert create_playlist(server.client(), journal, selection()).status == "failed"
    assert server.calls.count("createPlaylist") == 1


@pytest.mark.parametrize("version", ["", "0.65.0", "0.64.2-custom", "garbage"])
def test_unvalidated_server_is_rejected_before_mutation(tmp_path, version):
    server = SaveServer()
    server.version = version
    with pytest.raises(ApplicationError) as error:
        create_playlist(server.client(), SaveJournal(tmp_path / "j.sqlite3"), selection())
    assert error.value.code == "unsupported_server" and not server.created


def test_preflight_rejects_stale_duplicate_or_out_of_scope_ids_and_duplicate_names(tmp_path):
    server, journal = SaveServer(), SaveJournal(tmp_path / "j.sqlite3")
    for i, ids in enumerate((["one", "one"], ["gone"], [])):
        with pytest.raises(ApplicationError):
            create_playlist(server.client(), journal, selection(operation_id=f"invalid-{i}", song_ids=ids))
    server.stale = "two"
    with pytest.raises(ApplicationError):
        create_playlist(server.client(), journal, selection())
    server.stale, server.names = None, ["Paper Stars"]
    with pytest.raises(ApplicationError) as error:
        create_playlist(server.client(), journal, selection())
    assert error.value.code == "duplicate_name" and not server.created
    assert (
        create_playlist(server.client(), journal, selection(operation_id="ack", allow_duplicate_name=True)).status
        == "verified"
    )


def test_independent_sqlite_connections_claim_same_prepared_key_once(tmp_path):
    path, server = tmp_path / "j.sqlite3", SaveServer()
    barrier = Barrier(2)

    def worker():
        journal = SaveJournal(path)
        journal.prepare("same", caller_binding(server.client(), "2", "operator"), selection().payload)
        barrier.wait(timeout=5)
        return journal.claim("same")

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(lambda _: worker(), range(2))) == [False, True]


def test_concurrent_application_calls_create_once_and_persist_before_network(tmp_path):
    server, path = SaveServer(), tmp_path / "j.sqlite3"
    SaveJournal(path)
    barrier = Barrier(2)
    original_names = server.client().playlist_names

    def worker():
        source = server.client()

        def names():
            result = original_names()
            barrier.wait(timeout=5)
            return result

        source.playlist_names = names
        return create_playlist(source, SaveJournal(path), selection())

    def assert_submitting():
        operation = SaveJournal(path).get("operation-1", caller_binding(server.client(), "2", "operator"))
        assert operation.status == "submitting"

    server.before_create = assert_submitting
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: worker(), range(2)))
    assert len(server.created) == 1 and any(result.status == "verified" for result in results)


def test_malformed_count_retains_known_id_unresolved_and_can_recover(tmp_path):
    server, path = SaveServer(), tmp_path / "journal.sqlite3"
    server.overrides = {"songCount": "garbage"}
    operation = create_playlist(server.client(), SaveJournal(path), selection())
    assert operation.status == "unresolved" and operation.playlist_id == "p-0"
    assert operation.reason == "readback_unavailable"
    retried = create_playlist(server.client(), SaveJournal(path), selection())
    assert retried.status == "unresolved" and len(server.created) == 1
    server.overrides = {}
    recovered = get_operation(server.client(), SaveJournal(path), "operation-1", "2")
    assert recovered.status == "verified" and len(server.created) == 1
