"""Operator authentication and managed source dependencies for native endpoints."""

import hmac
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request

from resonance.navidrome import NavidromeClient


def require_operator(request: Request, authorization: str | None = Header(default=None)) -> str:
    configured = request.app.state.settings.api_token
    if configured is None or not configured.get_secret_value():
        raise HTTPException(status_code=503, detail="Configure RESONANCE__API_TOKEN to enable native HTTP operations")
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(token.encode(), configured.get_secret_value().encode()):
        raise HTTPException(
            status_code=401, detail="Operator bearer token required", headers={"WWW-Authenticate": "Bearer"}
        )
    return "operator"


def get_navidrome(request: Request, _caller: Annotated[str, Depends(require_operator)]) -> Iterator[NavidromeClient]:
    injected = getattr(request.app.state, "navidrome", None)
    if injected is not None:
        yield injected
        return
    client = NavidromeClient(request.app.state.settings.navidrome)
    try:
        yield client
    finally:
        client.close()
