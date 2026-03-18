"""
Ingest LRC lyrics into Qdrant.

Pipeline: parse LRC files → chunk into sections → embed with OpenAI → store in Qdrant

Usage:
    python -m lrc_match.ingest
    python -m lrc_match.ingest --collection lyrics_10 --model large --gap 10
"""

import os
from argparse import ArgumentParser
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from .chunker import chunk_song

load_dotenv()

DATA_DIR = Path("data")

MODELS = {
    "small": ("text-embedding-3-small", 1536),
    "large": ("text-embedding-3-large", 3072),
}


def embed_texts(client: OpenAI, texts: list[str], model: str) -> list[list[float]]:
    """Get embeddings for a batch of texts."""
    response = client.embeddings.create(model=model, input=texts)
    return [item.embedding for item in response.data]


def setup_collection(client: QdrantClient, collection_name: str, embedding_dim: int):
    """Create the Qdrant collection, replacing if it exists."""
    collections = [c.name for c in client.get_collections().collections]
    if collection_name in collections:
        print(f"Collection '{collection_name}' already exists, recreating...")
        client.delete_collection(collection_name)

    client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(size=embedding_dim, distance=Distance.COSINE),
    )
    print(f"Created collection '{collection_name}' ({embedding_dim}d, cosine)")


def main():
    parser = ArgumentParser(description="Ingest LRC lyrics into Qdrant")
    parser.add_argument("--collection", default="lyrics", help="Qdrant collection name")
    parser.add_argument(
        "--model",
        choices=["small", "large"],
        default="small",
        help="Embedding model: small (1536d) or large (3072d)",
    )
    parser.add_argument(
        "--gap",
        type=float,
        default=5.0,
        help="Gap threshold in seconds for temporal chunking",
    )
    args = parser.parse_args()

    model_name, embedding_dim = MODELS[args.model]
    print(
        f"Config: collection={args.collection}, model={model_name} ({embedding_dim}d), gap={args.gap}s"
    )

    openai_client = OpenAI(api_key=os.getenv("OPEN_AI_KEY"))
    qdrant_client = QdrantClient(url="http://localhost:6333")

    # Parse and chunk all LRC files
    print("Parsing and chunking LRC files...")
    chunks_to_embed = []
    skipped = 0

    for lrc_file in sorted(DATA_DIR.glob("*.lrc")):
        lyric = chunk_song(lrc_file, gap_threshold_sec=args.gap)

        if not lyric or not lyric.chunks:
            skipped += 1
            continue

        for chunk in lyric.chunks:
            chunks_to_embed.append(
                {
                    "artist": lyric.artist,
                    "title": lyric.title,
                    "filename": lyric.filename,
                    "section": chunk.section_name,
                    "position": chunk.position,
                    "total_sections": chunk.total_chunks,
                    "lyrics": chunk.lyrics,
                    "start_sec": chunk.start_sec,
                    "duration_sec": chunk.duration_sec,
                }
            )

    print(
        f"Created {len(chunks_to_embed)} chunks from "
        f"{len(list(DATA_DIR.glob('*.lrc'))) - skipped} songs "
        f"(skipped {skipped} empty/invalid)"
    )

    setup_collection(qdrant_client, args.collection, embedding_dim)

    BATCH_SIZE = 64
    for i in range(0, len(chunks_to_embed), BATCH_SIZE):
        batch = chunks_to_embed[i : i + BATCH_SIZE]
        lyrics_texts = [c["lyrics"] for c in batch]
        vectors = embed_texts(openai_client, lyrics_texts, model_name)

        points = [
            PointStruct(
                id=i + j,
                vector=vec,
                payload={
                    "artist": chunk["artist"],
                    "title": chunk["title"],
                    "filename": chunk["filename"],
                    "section": chunk["section"],
                    "position": chunk["position"],
                    "total_sections": chunk["total_sections"],
                    "lyrics": chunk["lyrics"][:500],
                    "start_sec": chunk["start_sec"],
                    "duration_sec": chunk["duration_sec"],
                },
            )
            for j, (chunk, vec) in enumerate(zip(batch, vectors))
        ]

        qdrant_client.upsert(collection_name=args.collection, points=points)
        print(f"  Upserted {i + len(batch)}/{len(chunks_to_embed)}")

    print(f"\nDone! {len(chunks_to_embed)} chunks indexed in Qdrant.")
    info = qdrant_client.get_collection(args.collection)
    print(f"Collection info: {info.points_count} points")


if __name__ == "__main__":
    main()
