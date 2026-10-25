"""
Search lyrics in Qdrant by semantic similarity.

Usage:
    resonance-search --profile ollama-nomic-text "songs about letting go"
    resonance-search --profile vyakyarth "love" --artist "Coldplay"
"""

import json
import sys
from argparse import ArgumentParser, Namespace
from contextlib import closing

from qdrant_client import QdrantClient

from .application.indexing import SCHEMA_VERSION, read_metadata
from .application.search import run_search
from .config import Settings
from .embedders import close_embedders, resolve_embedder
from .errors import ApplicationError
from .navidrome import source_binding


def main() -> None:
    parser = ArgumentParser(description="Search lyrics by semantic similarity")
    parser.add_argument("query", help="Natural language query")
    parser.add_argument(
        "--profile",
        "--provider",
        dest="profile",
        help="Override the collection's stored embedding profile (must remain compatible)",
    )
    parser.add_argument("--collection", required=True, help="Qdrant collection name")
    parser.add_argument("--artist", help="Filter by artist name")
    parser.add_argument("--limit", type=int, default=15, help="Number of results")
    args = parser.parse_args()

    try:
        _execute(args)
    except ApplicationError as error:
        sys.stderr.write(json.dumps({"error": error.code, "detail": str(error)}) + "\n")
        raise SystemExit(1) from None
    finally:
        close_embedders()


def _execute(args: Namespace) -> None:
    settings = Settings()
    with closing(
        QdrantClient(
            url=settings.qdrant.url,
            api_key=settings.qdrant.api_key.get_secret_value() if settings.qdrant.api_key else None,
        )
    ) as qdrant:
        collection = args.collection
        metadata = read_metadata(qdrant, collection)
        profile_id = args.profile or metadata.get("config_name") or settings.embedding.profile
        embedder = resolve_embedder(profile_id, settings.embedding)
        print(f'\nQuery: "{args.query}"')
        print(f"Collection: {collection} | Profile: {profile_id} | Model: {embedder.model_name}")
        if args.artist:
            print(f"Filter: artist = {args.artist}")

        results = run_search(
            qdrant=qdrant,
            embedder=embedder,
            query=args.query,
            collection=collection,
            artist=args.artist,
            limit=args.limit,
            source_binding=source_binding(settings.navidrome)
            if metadata.get("schema_version") == SCHEMA_VERSION
            else None,
        )

        print(f"Results: {len(results)}\n")

        if len(results) < args.limit:
            print("Fewer complete songs found within the search window.\n")

        for i, result in enumerate(results, 1):
            print(f"  {i}. [{result.score:.4f}] {result.artist} — {result.title}")
            if result.song_id:
                print(f"     Song ID: {result.song_id} | Source: {result.source_id} | Library: {result.library_id}")
            print(f"     Section: {result.section} (part {result.position + 1}/{result.total_sections})")
            for line in result.lyrics.split("\n")[:2]:
                print(f"     | {line}")
            print()


if __name__ == "__main__":
    main()
