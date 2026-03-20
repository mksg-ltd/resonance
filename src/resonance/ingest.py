"""
Ingest song lyrics into Qdrant.

Pipeline: scan audio files → extract lyrics (embedded/sidecar) → chunk → embed → store in Qdrant

Usage:
    resonance-ingest --provider ollama-bge-m3
    resonance-ingest --provider vyakyarth --collection tamil-lyrics
"""

from argparse import ArgumentParser
from pathlib import Path

from qdrant_client import QdrantClient

from .config import load_settings
from .embedders import create_embedder_for_name
from .routes.ingest import run_ingest


def main():
    parser = ArgumentParser(description="Ingest song lyrics into Qdrant")
    parser.add_argument(
        "--provider",
        required=True,
        help="Named provider config from conf.d/ (e.g., 'ollama-bge-m3', 'vyakyarth')",
    )
    parser.add_argument(
        "--collection",
        required=True,
        help="Qdrant collection name",
    )
    parser.add_argument(
        "--gap",
        type=float,
        help="Gap threshold in seconds for temporal chunking (overrides config)",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        required=True,
        help="Root music directory to scan for audio files with lyrics",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-ingestion even if collection has data",
    )
    args = parser.parse_args()

    settings = load_settings()
    embedder = create_embedder_for_name(args.provider)
    qdrant = QdrantClient(
        url=settings.qdrant.url,
        api_key=settings.qdrant.api_key.get_secret_value() if settings.qdrant.api_key else None,
    )

    collection = args.collection
    print(
        f"Config: collection={collection}, provider={args.provider}, "
        f"model={embedder.model_name} ({embedder.dimensions}d), "
        f"gap={args.gap or settings.chunking.gap_threshold_sec}s"
    )

    print("Starting ingestion...")
    result = run_ingest(
        qdrant=qdrant,
        embedder=embedder,
        settings=settings,
        config_name=args.provider,
        collection=args.collection,
        gap_threshold_sec=args.gap,
        force=args.force,
        data_dir=args.data_dir,
    )

    if result.files_processed == 0 and result.chunks_created == 0 and result.skipped == 0:
        print(f"Collection '{collection}' already has data. Use --force to re-ingest.")
    else:
        print(
            f"\nDone! {result.chunks_created} chunks from {result.files_processed} songs "
            f"(skipped {result.skipped} empty/invalid)"
        )

    info = qdrant.get_collection(collection)
    print(f"Collection info: {info.points_count} points")
    qdrant.close()


if __name__ == "__main__":
    main()
