"""
Search lyrics in Qdrant by semantic similarity.

Usage:
    python -m lrc_match.search "your query here"
    python -m lrc_match.search "your query" --artist "Coldplay"
    python -m lrc_match.search "your query" --collection lyrics_10 --model large
"""

import os
from argparse import ArgumentParser

from dotenv import load_dotenv
from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

load_dotenv()

MODELS = {
    "small": "text-embedding-3-small",
    "large": "text-embedding-3-large",
}


def search(query: str, collection: str, model: str, artist: str | None = None, limit: int = 15):
    openai_client = OpenAI(api_key=os.getenv("OPEN_AI_KEY"))
    qdrant_client = QdrantClient(url="http://localhost:6333")

    response = openai_client.embeddings.create(model=model, input=query)
    query_vector = response.data[0].embedding

    query_filter = None
    if artist:
        query_filter = Filter(must=[FieldCondition(key="artist", match=MatchValue(value=artist))])

    results = qdrant_client.query_points(
        collection_name=collection,
        query=query_vector,
        query_filter=query_filter,
        limit=limit,
    )

    print(f'\nQuery: "{query}"')
    print(f"Collection: {collection} | Model: {model}")
    if artist:
        print(f"Filter: artist = {artist}")
    print(f"Results: {len(results.points)}\n")

    for i, point in enumerate(results.points, 1):
        p = point.payload
        score = point.score
        print(f"  {i}. [{score:.4f}] {p['artist']} — {p['title']}")
        print(f"     Section: {p['section']} (part {p['position'] + 1}/{p['total_sections']})")
        lyrics_preview = p["lyrics"].split("\n")[:2]
        for line in lyrics_preview:
            print(f"     | {line}")
        print()


def main():
    parser = ArgumentParser(description="Search lyrics by semantic similarity")
    parser.add_argument("query", help="Natural language query")
    parser.add_argument("--artist", help="Filter by artist name")
    parser.add_argument("--collection", default="lyrics", help="Qdrant collection name")
    parser.add_argument(
        "--model",
        choices=["small", "large"],
        default="small",
        help="Embedding model (must match what was used for ingestion)",
    )
    parser.add_argument("--limit", type=int, default=15, help="Number of results")
    args = parser.parse_args()

    search(args.query, args.collection, MODELS[args.model], artist=args.artist, limit=args.limit)


if __name__ == "__main__":
    main()
