"""Trusted local operator adapter for native create/status operations."""

import json
import sys
from argparse import ArgumentParser
from dataclasses import asdict

from resonance.application.playlists import (
    PlaylistSelection,
    create_playlist,
    ensure_legacy_operations_resolved,
    get_operation,
)
from resonance.cli_auth import prompt_navidrome_credentials
from resonance.config import Settings
from resonance.errors import ApplicationError
from resonance.navidrome import NavidromeClient
from resonance.state import SaveJournal


def main() -> None:
    parser = ArgumentParser(description="Create and verify a private Navidrome playlist")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("create", "status"):
        command = commands.add_parser(name)
        command.add_argument("--operation-id", required=True, help="Stable key reused for every retry")
        command.add_argument("--library", required=True)
        if name == "create":
            command.add_argument("--name", required=True)
            command.add_argument(
                "--song", action="append", required=True, dest="song_ids", help="Repeat in playback order"
            )
            command.add_argument("--allow-duplicate-name", action="store_true")
    args = parser.parse_args()
    source = None
    try:
        settings = Settings()
        source = NavidromeClient(settings.navidrome, prompt_navidrome_credentials())
        journal = SaveJournal(settings.journal_path)
        ensure_legacy_operations_resolved(source, journal, settings.admin_user)
        if args.command == "create":
            result = create_playlist(
                source,
                journal,
                PlaylistSelection(
                    args.operation_id,
                    args.library,
                    args.name,
                    args.song_ids,
                    args.allow_duplicate_name,
                ),
            )
        else:
            result = get_operation(source, journal, args.operation_id, args.library)
        sys.stdout.write(json.dumps(asdict(result), ensure_ascii=False) + "\n")
        if result.status != "verified":
            raise SystemExit(1 if result.status == "failed" else 2)
    except ApplicationError as error:
        sys.stderr.write(json.dumps({"error": error.code, "detail": str(error)}) + "\n")
        raise SystemExit(1) from None
    finally:
        if source:
            source.close()


if __name__ == "__main__":
    main()
