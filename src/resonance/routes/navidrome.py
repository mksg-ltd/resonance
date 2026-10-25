"""Authenticated native-source adapters. All save policy lives in application/."""

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from resonance.application.library import get_lyrics, list_tracks
from resonance.application.playlists import (
    PlaylistSelection,
    create_playlist,
    ensure_legacy_operations_resolved,
    get_operation,
)
from resonance.auth import Principal
from resonance.errors import fail
from resonance.navidrome import NavidromeClient
from resonance.routes.auth import get_navidrome, get_principal, require_admin
from resonance.state import SaveJournal, SaveOperation

router = APIRouter(prefix="/api/navidrome")
Source = Annotated[NavidromeClient, Depends(get_navidrome)]
Caller = Annotated[Principal, Depends(get_principal)]


class CreatePlaylistRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation_id: str = Field(min_length=1, max_length=128)
    library_id: str = Field(min_length=1, max_length=256)
    name: str = Field(min_length=1, max_length=200)
    song_ids: list[str] = Field(min_length=1, max_length=100)
    allow_duplicate_name: bool = False


def journal(request: Request) -> SaveJournal:
    return SaveJournal(request.app.state.settings.journal_path)


@router.get("/connection")
def connection(source: Source) -> dict:
    return asdict(source.inspect())


@router.get("/libraries")
def libraries(source: Source, _admin: Annotated[Principal, Depends(require_admin)]) -> list[dict]:
    return [asdict(item) for item in source.libraries()]


@router.get("/tracks")
def tracks(source: Source, library_id: str, limit: Annotated[int, Query(ge=1, le=1000)] = 20) -> list[dict]:
    return [asdict(item) for item in list_tracks(source, library_id, limit)]


@router.get("/lyrics")
def lyrics(source: Source, library_id: str, song_id: str) -> dict:
    return asdict(get_lyrics(source, library_id, song_id))


@router.post("/playlists")
def save(body: CreatePlaylistRequest, request: Request, source: Source, caller: Caller) -> SaveOperation:
    selection = PlaylistSelection(**body.model_dump())
    save_journal = journal(request)
    if caller.is_admin:
        ensure_legacy_operations_resolved(source, save_journal, request.app.state.settings.admin_user)
    return create_playlist(source, save_journal, selection, caller=caller.username)


@router.get("/operations/{operation_id}")
def status(operation_id: str, library_id: str, request: Request, source: Source, caller: Caller) -> SaveOperation:
    if library_id not in {library.id for library in source.libraries()}:
        fail("Library not found", code="library_not_found", status=404)
    save_journal = journal(request)
    if caller.is_admin:
        ensure_legacy_operations_resolved(source, save_journal, request.app.state.settings.admin_user)
    return get_operation(source, save_journal, operation_id, library_id, caller=caller.username)
