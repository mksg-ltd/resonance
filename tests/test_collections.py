"""Library-scoped Qdrant collection discovery tests."""

from contextlib import closing

from qdrant_client import QdrantClient

from resonance.application.collections import visible_collections
from resonance.application.ingest import run_ingest
from resonance.config import Settings
from tests.test_indexing import FixtureEmbedder, FixtureSource, track


def test_visible_collections_are_limited_to_current_library_grants():
    with closing(QdrantClient(":memory:")) as qdrant:
        source = FixtureSource([track("one")])
        embedder = FixtureEmbedder()
        run_ingest(
            qdrant,
            embedder,
            Settings(_env_file=None),
            source=source,
            library_id="2",
            config_name="fixture",
            collection="library-two",
        )

        visible = visible_collections(qdrant, source.binding, {"2"})
        hidden = visible_collections(qdrant, source.binding, {"3"})

        assert [item.name for item in visible] == ["library-two"]
        assert visible[0].metadata["library_id"] == "2"
        assert hidden == []
