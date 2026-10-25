"""Search CLI results carry source IDs that can be passed to the save CLI."""

import json
from contextlib import closing

from qdrant_client import QdrantClient

from resonance import playlists, search
from resonance.application.ingest import run_ingest
from resonance.config import Settings
from tests.test_indexing import FixtureEmbedder, FixtureSource
from tests.test_save_operations import SaveServer


def test_search_cli_ids_can_be_used_directly_by_save_cli(tmp_path, monkeypatch, capsys):
    embedder = FixtureEmbedder()
    source_server = SaveServer()
    source = source_server.client()
    settings = Settings(navidrome=source.config, journal_path=tmp_path / "operations.sqlite3", _env_file=None)
    with closing(QdrantClient(":memory:")) as qdrant:
        run_ingest(
            qdrant,
            embedder,
            settings,
            source=FixtureSource(),
            library_id="2",
            config_name="fixture",
            collection="native",
        )
        monkeypatch.setattr(search, "Settings", lambda: settings)
        monkeypatch.setattr(search, "resolve_embedder", lambda *_: embedder)
        monkeypatch.setattr(search, "QdrantClient", lambda **_: qdrant)
        monkeypatch.setattr(qdrant, "close", lambda: None)
        monkeypatch.setattr("sys.argv", ["resonance-search", "paper stars", "--collection", "native", "--limit", "3"])
        search.main()
        output = capsys.readouterr().out
        lines = [line.strip() for line in output.splitlines() if "Song ID:" in line]
        ids = [line.split("Song ID: ", 1)[1].split(" | ", 1)[0] for line in lines]
        assert set(ids) == {"one", "two"}
        assert all("Source: home | Library: 2" in line for line in lines)
        monkeypatch.setattr(playlists, "Settings", lambda: settings)
        monkeypatch.setattr(playlists, "NavidromeClient", lambda *_: source)
        monkeypatch.setattr(playlists, "prompt_navidrome_credentials", lambda: source.credentials)
        monkeypatch.setattr(
            "sys.argv",
            [
                "resonance-playlist",
                "create",
                "--operation-id",
                "cli-handoff",
                "--library",
                "2",
                "--name",
                "CLI Handoff",
                *[value for item in ids for value in ("--song", item)],
            ],
        )
        playlists.main()
        assert json.loads(capsys.readouterr().out)["status"] == "verified"
        assert source_server.created[0]["song_ids"] == ids
