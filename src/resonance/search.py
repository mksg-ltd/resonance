"""
Search lyrics in Qdrant by semantic similarity.

Usage:
    resonance-search --provider ollama-bge-m3 "songs about letting go"
    resonance-search --provider ollama-bge-m3 "love" --artist "Coldplay"
"""

from argparse import ArgumentParser

from qdrant_client import QdrantClient

from .config import Settings
from .embedders import create_embedder_for_name
from .routes.search import run_search


def main():
    parser = ArgumentParser(description="Search lyrics by semantic similarity")
    parser.add_argument("query", help="Natural language query")
    parser.add_argument(
        "--provider",
        required=True,
        help="Named provider config from conf.d/ (e.g., 'ollama-bge-m3', 'vyakyarth')",
    )
    parser.add_argument("--collection", required=True, help="Qdrant collection name")
    parser.add_argument("--artist", help="Filter by artist name")
    parser.add_argument("--limit", type=int, default=15, help="Number of results")
    args = parser.parse_args()

    settings = Settings()
    embedder = create_embedder_for_name(args.provider)
    qdrant = QdrantClient(
        url=settings.qdrant.url,
        api_key=settings.qdrant.api_key.get_secret_value() if settings.qdrant.api_key else None,
    )

    collection = args.collection
    print(f'\nQuery: "{args.query}"')
    print(f"Collection: {collection} | Provider: {args.provider} | Model: {embedder.model_name}")
    if args.artist:
        print(f"Filter: artist = {args.artist}")

    results = run_search(
        qdrant=qdrant,
        embedder=embedder,
        query=args.query,
        collection=collection,
        artist=args.artist,
        limit=args.limit,
    )

    print(f"Results: {len(results)}\n")

    for i, result in enumerate(results, 1):
        print(f"  {i}. [{result.score:.4f}] {result.artist} — {result.title}")
        print(f"     Section: {result.section} (part {result.position + 1}/{result.total_sections})")
        for line in result.lyrics.split("\n")[:2]:
            print(f"     | {line}")
        print()

    qdrant.close()


if __name__ == "__main__":
    main()
