"""Interactive Navidrome credentials for commands that call the server."""

import getpass
import sys

from resonance.errors import ApplicationError
from resonance.navidrome import NavidromeCredentials


def prompt_navidrome_credentials() -> NavidromeCredentials:
    """Read a username and masked password without persisting or echoing secrets."""
    if not sys.stdin.isatty():
        msg = "Navidrome credentials require an interactive terminal"
        raise ApplicationError(
            msg,
            code="credentials_required",
            status=400,
        )
    try:
        username = input("Navidrome username: ").strip()
        password = getpass.getpass("Navidrome password: ")
    except EOFError:
        msg = "Navidrome credentials were not provided"
        raise ApplicationError(msg, code="credentials_required", status=400) from None
    if not username or not password:
        msg = "Navidrome username and password are required"
        raise ApplicationError(msg, code="credentials_required", status=400)
    return NavidromeCredentials(username, password)
