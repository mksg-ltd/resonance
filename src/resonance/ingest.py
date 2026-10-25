"""CLI adapter for a scoped Navidrome-to-Qdrant ingestion operation."""

import json
import sys
from argparse import ArgumentParser
from dataclasses import asdict

from qdrant_client import QdrantClient

from resonance.application.ingest import run_ingest
from resonance.config import Settings
from resonance.embedders import close_embedders, resolve_embedder
from resonance.errors import ApplicationError
from resonance.navidrome import NavidromeClient


def main() -> None:
    parser = ArgumentParser(description="Index synced lyrics from one Navidrome library")
    parser.add_argument("--profile", "--provider", dest="profile", help="Embedding profile ID from the bundled catalog")
    parser.add_argument("--library", required=True, help="Navidrome music-folder ID")
    parser.add_argument("--collection", help="New or identically bound Qdrant collection")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--gap", type=float)
    parser.add_argument("--max-tracks", type=int, help="Bound this run; no deletion or pruning occurs")
    args = parser.parse_args()
    settings = Settings()
    profile_id = args.profile or settings.embedding.profile
    source = None
    qdrant = None
    try:
        source = NavidromeClient(settings.navidrome)
        qdrant = QdrantClient(
            url=settings.qdrant.url,
            api_key=settings.qdrant.api_key.get_secret_value() if settings.qdrant.api_key else None,
        )
        result = run_ingest(
            qdrant,
            resolve_embedder(profile_id, settings.embedding),
            settings,
            source=source,
            library_id=args.library,
            config_name=profile_id,
            collection=args.collection,
            batch_size=args.batch_size,
            gap_threshold_sec=args.gap,
            max_tracks=args.max_tracks,
        )
        sys.stdout.write(json.dumps(asdict(result)) + "\n")
    except ApplicationError as error:
        sys.stderr.write(json.dumps({"error": error.code, "detail": str(error)}) + "\n")
        raise SystemExit(1) from None
    finally:
        close_embedders()
        if source:
            source.close()
        if qdrant:
            qdrant.close()


if __name__ == "__main__":
    main()
