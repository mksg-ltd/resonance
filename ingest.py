"""
Ingest LRC lyrics into Qdrant.

Pipeline: parse LRC files → chunk into sections → embed with OpenAI → store in Qdrant

Each song gets split into multiple vectors (one per section), so a search
can match a specific verse or chorus rather than the song as a whole.

Usage:
    python ingest.py                                  # defaults: lyrics, small, 5s gap
    python ingest.py --collection lyrics_10 --model large --gap 10
"""

import os
import re
from argparse import ArgumentParser
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from chunk import chunk_song

load_dotenv()

DATA_DIR = Path("data")

# Model configs: name → (api model name, dimensions)
MODELS = {
    "small": ("text-embedding-3-small", 1536),
    "large": ("text-embedding-3-large", 3072),
}


# --- Metadata extraction ---


def extract_metadata(filepath: Path) -> dict:
    """Extract artist and title from filename.

    Pattern: "03 - Coldplay - Ghost Story.lrc" → artist="Coldplay", title="Ghost Story"
    """
    name = filepath.stem
    parts = re.split(r"\s*-\s*", name, maxsplit=2)
    if len(parts) >= 3:
        artist, title = parts[1].strip(), parts[2].strip()
    elif len(parts) == 2:
        artist, title = parts[0].strip(), parts[1].strip()
    else:
        artist, title = "Unknown", name

    # Clean up common suffixes like "(Album Version)", "(Explicit)"
    title = re.sub(r"\s*\((?:Album Version|Explicit)\)\s*$", "", title)

    return {"artist": artist, "title": title, "filename": filepath.name}


# --- Embedding ---


def embed_texts(client: OpenAI, texts: list[str], model: str) -> list[list[float]]:
    """Get embeddings for a batch of texts.

    OpenAI's API accepts up to 2048 texts per batch call.
    Batching is important because:
    - 1 API call with 100 texts is much faster than 100 calls with 1 text
    - Same cost either way (priced per token, not per call)
    """
    response = client.embeddings.create(model=model, input=texts)
    return [item.embedding for item in response.data]


# --- Qdrant Setup ---


def setup_collection(client: QdrantClient, collection_name: str, embedding_dim: int):
    """Create the Qdrant collection if it doesn't exist.

    A collection in Qdrant is like a table in SQL — it holds points (vectors + payloads).

    Key concept - VectorParams:
      - size: must match your embedding model's output dimensions
      - distance: how similarity is measured between vectors

    Distance metrics matter:
      - COSINE: measures angle between vectors. Most common for text embeddings.
        "How similar is the direction?" Ignores magnitude.
        Score range: -1 to 1 (1 = identical direction)

      - EUCLID: straight-line distance in vector space.
        "How far apart are these points?" Affected by magnitude.
        Lower = more similar.

      - DOT: dot product. Like cosine but NOT normalized — magnitude matters.
        Used when vector length carries meaning (e.g., popularity-weighted embeddings).

    We use COSINE because OpenAI embeddings are designed for cosine similarity,
    and we care about semantic direction, not magnitude.
    """
    collections = [c.name for c in client.get_collections().collections]
    if collection_name in collections:
        print(f"Collection '{collection_name}' already exists, recreating...")
        client.delete_collection(collection_name)

    client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(
            size=embedding_dim,
            distance=Distance.COSINE,
        ),
    )
    print(f"Created collection '{collection_name}' ({embedding_dim}d, cosine)")


# --- Main ---


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

    # 1. Parse and chunk all LRC files
    #
    # Instead of one vector per song, we create one vector per SECTION.
    # This means a search for "heartbreak" can match a specific verse
    # rather than averaging out with the upbeat chorus of the same song.
    print("Parsing and chunking LRC files...")
    chunks_to_embed = []
    skipped = 0

    for lrc_file in sorted(DATA_DIR.glob("*.lrc")):
        metadata = extract_metadata(lrc_file)
        chunks = chunk_song(lrc_file, gap_threshold_sec=args.gap)

        if not chunks:
            skipped += 1
            continue

        for chunk in chunks:
            chunks_to_embed.append(
                {
                    "artist": metadata["artist"],
                    "title": metadata["title"],
                    "filename": metadata["filename"],
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

    # 2. Set up Qdrant collection
    setup_collection(qdrant_client, args.collection, embedding_dim)

    # 3. Embed and upsert in batches
    #
    # Why batch?
    # - OpenAI: fewer API calls = faster + avoids rate limits
    # - Qdrant: upsert is optimized for bulk inserts, reduces network round-trips
    #
    # What is "upsert"?
    # Insert-or-update. If a point with the same ID exists, it gets replaced.
    # This makes the script idempotent — safe to re-run.
    BATCH_SIZE = 64

    for i in range(0, len(chunks_to_embed), BATCH_SIZE):
        batch = chunks_to_embed[i : i + BATCH_SIZE]
        lyrics_texts = [c["lyrics"] for c in batch]

        # Embed this batch
        vectors = embed_texts(openai_client, lyrics_texts, model_name)

        # Build Qdrant points
        #
        # A Point in Qdrant has three parts:
        #   - id: unique identifier (we use sequential ints, but UUIDs work too)
        #   - vector: the embedding (list of floats)
        #   - payload: arbitrary JSON metadata — this is what makes Qdrant powerful.
        #     You can filter on any payload field during search.
        #     Think of it as the non-vector columns in your pgvector table.
        #
        # Notice how we store section-level metadata (section name, position)
        # alongside song-level metadata (artist, title). This lets us query like:
        #   "find choruses similar to X" (filter on section)
        #   "find Coldplay sections similar to X" (filter on artist)
        #   "find opening sections similar to X" (filter on position)
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
                    "lyrics": chunk["lyrics"][:500],  # truncated for display
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
