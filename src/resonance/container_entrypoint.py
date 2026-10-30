"""Prepare bind-mounted application state, then start the server unprivileged."""

import logging
import os
import pwd
import sqlite3
import sys
from pathlib import Path

logger = logging.getLogger("resonance.container_entrypoint")
STATE_DIR = Path("/app/state")
LEGACY_DB = Path("/app/legacy-state/playlist-operations.sqlite3")
DB_NAME = "playlist-operations.sqlite3"


def _prepare_state(uid: int, gid: int) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    os.chown(STATE_DIR, uid, gid)
    destination = STATE_DIR / DB_NAME
    if destination.exists() or not LEGACY_DB.is_file():
        return

    temporary = STATE_DIR / f"{DB_NAME}.migrating"
    temporary.unlink(missing_ok=True)
    source_uri = f"file:{LEGACY_DB}?mode=ro"
    with sqlite3.connect(source_uri, uri=True) as source, sqlite3.connect(temporary) as target:
        source.backup(target)
    os.chown(temporary, uid, gid)
    Path(temporary).chmod(0o600)
    Path(temporary).replace(destination)
    logger.info("Imported playlist operation journal from the previous Compose volume")


def main() -> None:
    """Import legacy state once, drop root privileges, and exec the requested process."""
    if len(sys.argv) < 2:
        raise SystemExit(2)
    account = pwd.getpwnam("appuser")
    _prepare_state(account.pw_uid, account.pw_gid)
    if os.geteuid() == 0:
        os.setgroups([])
        os.setgid(account.pw_gid)
        os.setuid(account.pw_uid)
    os.execvp(sys.argv[1], sys.argv[1:])  # noqa: S606 - Docker supplies the executable directly.


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
