"""FastMCP authentication delegates to the shared Resonance session runtime."""

import pytest
from fastmcp.server.auth.auth import AccessToken

from resonance.auth import AuthRuntime
from resonance.mcp.auth import ResonanceTokenVerifier


@pytest.mark.asyncio
async def test_verifier_resolves_active_resonance_session() -> None:
    runtime = AuthRuntime(admin_user="admin")
    session = runtime.sessions.create("alice", "navidrome-password")
    token = runtime.issue(session)
    verifier = ResonanceTokenVerifier(runtime)

    access_token = await verifier.verify_token(token)

    assert isinstance(access_token, AccessToken)
    assert access_token.subject == "alice"
    assert access_token.claims["sid"] == session.session_id
    assert access_token.token == token


@pytest.mark.asyncio
async def test_verifier_rejects_invalid_and_revoked_tokens() -> None:
    runtime = AuthRuntime(admin_user=None)
    session = runtime.sessions.create("alice", "navidrome-password")
    token = runtime.issue(session)
    verifier = ResonanceTokenVerifier(runtime)

    assert await verifier.verify_token("not-a-token") is None

    runtime.sessions.revoke(session.session_id)

    assert await verifier.verify_token(token) is None
