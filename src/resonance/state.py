"""Transactional playlist-save journal. No track mapping or lyric storage."""

import hashlib
import json
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from resonance.errors import external_errors, fail


def canonical(value: Any) -> str:
    """Preserve opaque IDs and exact user names while canonicalizing JSON structure."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


@dataclass
class SaveOperation:
    operation_id: str
    binding: dict[str, str]
    request: dict[str, Any]
    request_hash: str
    status: str
    playlist_id: str | None
    reason: str | None
    updated_at: str


class SaveJournal:
    """Short SQLite transactions; never hold a transaction across an HTTP call."""

    @external_errors("Playlist journal is unavailable")
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS save_operations (
                    operation_id TEXT PRIMARY KEY,
                    binding TEXT NOT NULL,
                    request TEXT NOT NULL,
                    request_hash TEXT NOT NULL,
                    status TEXT NOT NULL,
                    playlist_id TEXT,
                    reason TEXT,
                    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                )
            """)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
                connection.commit()
            except BaseException:
                connection.rollback()
                raise

    @staticmethod
    def _operation(row: sqlite3.Row) -> SaveOperation:
        return SaveOperation(
            row["operation_id"],
            json.loads(row["binding"]),
            json.loads(row["request"]),
            row["request_hash"],
            row["status"],
            row["playlist_id"],
            row["reason"],
            row["updated_at"],
        )

    @external_errors("Playlist journal is unavailable")
    def prepare(self, operation_id: str, binding: dict[str, str], request: dict[str, Any]) -> SaveOperation:
        with self._transaction() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO save_operations(operation_id,binding,request,request_hash,status) "
                "VALUES (?,?,?,?,'prepared')",
                (operation_id, canonical(binding), canonical(request), digest(request)),
            )
            row = connection.execute("SELECT * FROM save_operations WHERE operation_id=?", (operation_id,)).fetchone()
            if row["binding"] != canonical(binding) or row["request_hash"] != digest(request):
                fail(
                    "Operation key already belongs to another request or account/source",
                    code="operation_conflict",
                    status=409,
                )
            return self._operation(row)

    @external_errors("Playlist journal is unavailable")
    def get(self, operation_id: str, binding: dict[str, str]) -> SaveOperation:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT * FROM save_operations WHERE operation_id=?", (operation_id,)).fetchone()
        if row is None:
            fail("Save operation does not exist", code="operation_not_found", status=404)
        if row["binding"] != canonical(binding):
            fail("Save operation belongs to another caller or source", code="operation_conflict", status=409)
        return self._operation(row)

    @external_errors("Playlist journal is unavailable")
    def claim(self, operation_id: str) -> bool:
        with self._transaction() as connection:
            return (
                connection.execute(
                    "UPDATE save_operations SET status='submitting', "
                    "updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE operation_id=? AND status='prepared'",
                    (operation_id,),
                ).rowcount
                == 1
            )

    @external_errors("Playlist journal is unavailable")
    def record_id(self, operation_id: str, playlist_id: str) -> None:
        with self._transaction() as connection:
            connection.execute(
                "UPDATE save_operations SET playlist_id=?,status='verifying',reason=NULL, "
                "updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE operation_id=? "
                "AND playlist_id IS NULL AND status IN ('submitting','unresolved')",
                (playlist_id, operation_id),
            )

    @external_errors("Playlist journal is unavailable")
    def outcome(self, operation_id: str, status: str, reason: str | None = None) -> None:
        with self._transaction() as connection:
            connection.execute(
                "UPDATE save_operations SET status=?,reason=?,updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') "
                "WHERE operation_id=? AND status != 'verified'",
                (status, reason, operation_id),
            )
