"""Native ingestion/search integration with real local Qdrant, no audio files."""

from contextlib import closing
from copy import deepcopy
from dataclasses import replace

import pytest
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

from resonance.application.indexing import digest, lyric_hash, read_metadata, song_state
from resonance.application.ingest import run_ingest
from resonance.application.search import run_search
from resonance.config import NavidromeConfig, Settings
from resonance.errors import ApplicationError
from resonance.models import LrcLine, Track
from resonance.navidrome import source_binding


class FixtureEmbedder:
    provider_name = "fixture"
    model_name = "synthetic-v1"
    dimensions = 3

    def __init__(self):
        self.calls = []
        self.profile = {
            "provider": self.provider_name,
            "model": self.model_name,
            "dimensions": 3,
            "endpoint": "fixture",
        }

    def embed(self, texts):
        self.calls.append(texts)
        return [[0.8, 0.2, 0.0] if "other recording" in text else [1.0, 0.0, 0.0] for text in texts]


class FixtureSource:
    def __init__(self, tracks=None):
        self.config = NavidromeConfig(
            base_url="https://music.test", user_id="operator", user_password="test-secret", _env_file=None
        )
        self.binding = source_binding(self.config)
        self.items = tracks if tracks is not None else [track("one"), track("two")]

    def tracks(self, library_id):
        assert library_id == "2"
        yield from deepcopy(self.items)

    def lyrics(self, item):
        return item


def track(song_id, lines=None):
    return Track(
        "home",
        "2",
        song_id,
        "Artist",
        "Same Title",
        "Album",
        lines
        or [
            LrcLine(0, "[Verse] I fold a paper kite"),
            LrcLine(2, "And let it find the light"),
            LrcLine(20, "[Chorus] The paper stars return"),
            LrcLine(22, "With lessons I can learn"),
        ],
        "synced",
        "xxx",
    )


def ingest(qdrant, source, embedder, **kwargs):
    return run_ingest(
        qdrant,
        embedder,
        Settings(_env_file=None),
        source=source,
        library_id="2",
        config_name="fixture",
        collection="native",
        **kwargs,
    )


def test_navidrome_native_ingestion_identity_search_and_unchanged_retry():
    with closing(QdrantClient(":memory:")) as qdrant:
        source, embedder = FixtureSource(), FixtureEmbedder()
        result = ingest(qdrant, source, embedder)
        assert result.tracks_processed == 2 and result.sections_written == 4
        assert result.enumeration_complete
        metadata = read_metadata(qdrant, "native")
        assert metadata["library_id"] == "2" and metadata["model"] == "synthetic-v1"
        state = song_state(qdrant, "native", metadata, "one")
        assert state.complete
        payload = state.records[0].payload
        assert all(field in payload for field in ("song_id", "lyrics_hash", "index_fingerprint", "indexed_at"))
        assert "audio_path" not in payload and "filename" not in payload
        calls = len(embedder.calls)
        retried = ingest(qdrant, source, embedder)
        assert retried.tracks_unchanged == 2 and retried.sections_written == 0
        assert len(embedder.calls) == calls
        results = run_search(qdrant, embedder, "query", "native", limit=2, source_binding=source.binding)
        assert {row.song_id for row in results} == {"one", "two"}
        assert all(row.title == "Same Title" and row.lyrics_source == "navidrome" for row in results)


def test_partial_sections_are_hidden_then_identical_retry_repairs_them():
    with closing(QdrantClient(":memory:")) as qdrant:
        source, embedder = FixtureSource([track("one")]), FixtureEmbedder()
        ingest(qdrant, source, embedder)
        metadata = read_metadata(qdrant, "native")
        state = song_state(qdrant, "native", metadata, "one")
        qdrant.delete(collection_name="native", points_selector=[state.records[0].id], wait=True)
        assert not song_state(qdrant, "native", metadata, "one").complete
        assert run_search(qdrant, embedder, "query", "native", source_binding=source.binding) == []
        ingest(qdrant, source, embedder)
        assert song_state(qdrant, "native", metadata, "one").complete
        assert qdrant.get_collection("native").points_count == 3


def test_changed_lyrics_model_and_scope_fail_without_overwriting_old_index():
    with closing(QdrantClient(":memory:")) as qdrant:
        source, embedder = FixtureSource([track("one")]), FixtureEmbedder()
        ingest(qdrant, source, embedder)
        count = qdrant.get_collection("native").points_count
        source.items[0].lines.append(LrcLine(40, "A new ending appears"))
        with pytest.raises(ApplicationError) as error:
            ingest(qdrant, source, embedder)
        assert error.value.code == "refresh_required"
        assert qdrant.get_collection("native").points_count == count
        source.items[0].lines.pop()
        changed = FixtureEmbedder()
        changed.profile["model"] = "different-space-same-size"
        with pytest.raises(ApplicationError) as error:
            ingest(qdrant, source, changed)
        assert error.value.code == "collection_incompatible" and not changed.calls
        with pytest.raises(ApplicationError):
            run_search(qdrant, changed, "query", "native", source_binding=source.binding)
        with pytest.raises(ApplicationError):
            run_search(qdrant, embedder, "query", "native", source_binding={**source.binding, "source_id": "other"})


def test_hashes_ignore_display_metadata_and_normalize_unicode():
    item = track("one", [LrcLine(0, "cafe\u0301")])
    assert lyric_hash(item) == lyric_hash(replace(item, artist="Renamed", album="Retagged", lines=[LrcLine(0, "café")]))
    assert lyric_hash(item) != lyric_hash(replace(item, lines=[LrcLine(1, "café")]))
    assert digest({"model": "one"}) != digest({"model": "two"})


def test_missing_lyrics_and_bounded_run_do_not_mark_success_or_prune():
    with closing(QdrantClient(":memory:")) as qdrant:
        source, embedder = (
            FixtureSource([replace(track("missing"), lines=[], lyrics_status="missing"), track("one")]),
            FixtureEmbedder(),
        )
        result = ingest(qdrant, source, embedder, max_tracks=1)
        assert result.tracks_processed == 0 and result.missing_lyrics == 1
        assert not result.enumeration_complete and not embedder.calls
        metadata = read_metadata(qdrant, "native")
        assert not song_state(qdrant, "native", metadata, "missing").complete
        result = ingest(qdrant, source, embedder)
        assert result.tracks_processed == 1 and result.missing_lyrics == 1


def test_search_overfetches_repeated_sections_to_find_unique_recordings():
    sections = [LrcLine(i * 2, f"[Verse {i}] paper stars") for i in range(80)]
    other = track("other", [LrcLine(0, "other recording")])
    with closing(QdrantClient(":memory:")) as qdrant:
        source, embedder = FixtureSource([track("many", sections), other]), FixtureEmbedder()
        ingest(qdrant, source, embedder)
        hits = run_search(qdrant, embedder, "query", "native", limit=2, source_binding=source.binding)
        assert [row.song_id for row in hits] == ["many", "other"]
        assert (
            run_search(qdrant, embedder, "query", "native", artist="Missing Artist", source_binding=source.binding)
            == []
        )


def test_corrupt_section_set_is_not_complete_or_searchable():
    with closing(QdrantClient(":memory:")) as qdrant:
        source, embedder = FixtureSource([track("one")]), FixtureEmbedder()
        ingest(qdrant, source, embedder)
        metadata = read_metadata(qdrant, "native")
        record = song_state(qdrant, "native", metadata, "one").records[0]
        qdrant.set_payload("native", {"total_sections": 99}, points=[record.id], wait=True)
        assert not song_state(qdrant, "native", metadata, "one").complete
        assert not run_search(qdrant, embedder, "query", "native", source_binding=source.binding)


def test_interrupted_batch_is_hidden_and_retry_reuses_ids(monkeypatch):
    with closing(QdrantClient(":memory:")) as qdrant:
        source, embedder = FixtureSource([track("one")]), FixtureEmbedder()
        original = embedder.embed

        def interrupted(texts):
            if len(embedder.calls) == 1:
                raise RuntimeError("sensitive upstream failure")
            return original(texts)

        monkeypatch.setattr(embedder, "embed", interrupted)
        with pytest.raises(ApplicationError) as error:
            ingest(qdrant, source, embedder, batch_size=1)
        assert "sensitive" not in str(error.value)
        assert not run_search(qdrant, FixtureEmbedder(), "query", "native", source_binding=source.binding)
        monkeypatch.setattr(embedder, "embed", original)
        ingest(qdrant, source, embedder, batch_size=1)
        assert qdrant.get_collection("native").points_count == 3
        assert song_state(qdrant, "native", read_metadata(qdrant, "native"), "one").complete


def test_wrong_vector_dimensions_never_write_song_points():
    with closing(QdrantClient(":memory:")) as qdrant:
        source, embedder = FixtureSource([track("one")]), FixtureEmbedder()
        embedder.embed = lambda texts: [[1.0] for _ in texts]
        with pytest.raises(ApplicationError) as error:
            ingest(qdrant, source, embedder)
        assert error.value.code == "invalid_embeddings"
        assert qdrant.get_collection("native").points_count == 1
