"""FastMCP bearer verification backed by Resonance's active Navidrome sessions."""

from fastmcp.server.auth.auth import AccessToken, TokenVerifier

from resonance.auth import AuthRuntime


class ResonanceTokenVerifier(TokenVerifier):
    """Resolve existing Resonance bearer JWTs without creating another auth store."""

    def __init__(self, runtime: AuthRuntime) -> None:
        super().__init__()
        self._runtime = runtime

    async def verify_token(self, token: str) -> AccessToken | None:
        session = self._runtime.session_for_token(token)
        if session is None:
            return None
        claims = self._runtime.decode(token)
        if claims is None:
            return None
        return AccessToken(
            token=token,
            client_id="resonance",
            scopes=[],
            expires_at=session.expires_at,
            subject=session.username,
            claims=claims,
        )
