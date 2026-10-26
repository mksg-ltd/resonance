"""The mounted FastMCP endpoint shares FastAPI auth and transport policy."""

from collections.abc import Callable
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

from resonance.app import create_app
from resonance.config import Settings


@pytest.fixture(autouse=True)
def mock_qdrant(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeQdrant:
        def close(self) -> None:
            pass

    monkeypatch.setattr("resonance.app.QdrantClient", lambda **_kwargs: FakeQdrant())


def _client_factory(app: FastAPI) -> Callable[..., httpx.AsyncClient]:
    def create_client(**kwargs: Any) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), **kwargs)

    return create_client


@pytest.mark.asyncio
async def test_valid_bearer_lists_empty_tool_set() -> None:
    app = create_app(Settings(debug=True))
    session = app.state.auth_runtime.sessions.create("alice", "navidrome-password")
    token = app.state.auth_runtime.issue(session)
    transport = StreamableHttpTransport(
        "http://127.0.0.1:8000/mcp/",
        headers={"Authorization": f"Bearer {token}"},
        httpx_client_factory=_client_factory(app),
    )

    async with app.router.lifespan_context(app), Client(transport) as client:
        assert await client.list_tools() == []


@pytest.mark.asyncio
async def test_valid_bearer_is_accepted_over_https_in_production_mode() -> None:
    app = create_app(Settings(debug=False))
    session = app.state.auth_runtime.sessions.create("alice", "navidrome-password")
    token = app.state.auth_runtime.issue(session)
    transport = StreamableHttpTransport(
        "https://localhost:8000/mcp/",
        headers={"Authorization": f"Bearer {token}"},
        httpx_client_factory=_client_factory(app),
    )

    async with app.router.lifespan_context(app), Client(transport) as client:
        assert await client.list_tools() == []


@pytest.mark.asyncio
async def test_mcp_rejects_missing_revoked_and_remote_plain_http_auth() -> None:
    app = create_app(Settings(debug=True))
    session = app.state.auth_runtime.sessions.create("alice", "navidrome-password")
    token = app.state.auth_runtime.issue(session)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8000"
        ) as local_client:
            missing = await local_client.post("/mcp/", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"})
            assert missing.status_code == 401

            local_client.cookies.set("resonance_session", token)
            cookie_only = await local_client.post(
                "/mcp/",
                json={"jsonrpc": "2.0", "id": 2, "method": "initialize"},
            )
            assert cookie_only.status_code == 401

            app.state.auth_runtime.sessions.revoke(session.session_id)
            revoked = await local_client.post(
                "/mcp/",
                headers={"Authorization": f"Bearer {token}"},
                json={"jsonrpc": "2.0", "id": 3, "method": "initialize"},
            )
            assert revoked.status_code == 401

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://resonance.example"
        ) as remote_client:
            remote = await remote_client.post(
                "/mcp/",
                headers={"Authorization": f"Bearer {token}"},
                json={"jsonrpc": "2.0", "id": 4, "method": "initialize"},
            )
            assert remote.status_code == 400
            assert remote.json()["detail"] == "HTTPS is required"
