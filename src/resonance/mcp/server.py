"""FastMCP server factory and ASGI mount configuration."""

from fastmcp import FastMCP

from resonance.auth import AuthRuntime
from resonance.mcp.auth import ResonanceTokenVerifier


def create_mcp_server(runtime: AuthRuntime) -> FastMCP:
    """Create the tool-free FastMCP scaffold using the active API auth runtime."""
    return FastMCP(
        name="Resonance",
        instructions=(
            "Resonance provides semantic discovery for a Navidrome music library. "
            "No tools are available in this scaffold yet."
        ),
        auth=ResonanceTokenVerifier(runtime),
    )
