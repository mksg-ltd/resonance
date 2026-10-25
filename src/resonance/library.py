"""CLI adapter for read-only Navidrome inspection."""

import json
import sys
from argparse import ArgumentParser
from dataclasses import asdict

from resonance.application.library import get_lyrics, list_tracks
from resonance.cli_auth import prompt_navidrome_credentials
from resonance.config import Settings
from resonance.errors import ApplicationError
from resonance.navidrome import NavidromeClient


def main() -> None:
    parser = ArgumentParser(description="Inspect a Navidrome library without indexing or writing playlists")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("inspect")
    commands.add_parser("libraries")
    for name in ("tracks", "lyrics"):
        command = commands.add_parser(name)
        command.add_argument("--library", required=True)
        if name == "tracks":
            command.add_argument("--limit", type=int, default=20)
        else:
            command.add_argument("--song", required=True)
    args = parser.parse_args()
    client = None
    try:
        settings = Settings()
        client = NavidromeClient(settings.navidrome, prompt_navidrome_credentials())
        if args.command == "inspect":
            result = asdict(client.inspect())
        elif args.command == "libraries":
            result = [asdict(item) for item in client.libraries()]
        elif args.command == "tracks":
            result = [asdict(item) for item in list_tracks(client, args.library, args.limit)]
        else:
            result = asdict(get_lyrics(client, args.library, args.song))
        sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
    except ApplicationError as error:
        sys.stderr.write(json.dumps({"error": error.code, "detail": str(error)}) + "\n")
        raise SystemExit(1) from None
    finally:
        if client:
            client.close()


if __name__ == "__main__":
    main()
