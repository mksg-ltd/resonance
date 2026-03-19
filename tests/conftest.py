"""Shared test fixtures."""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from resonance.app import create_app
from resonance.config import Settings


@pytest.fixture
def test_settings() -> Settings:
    """Settings with test defaults."""
    return Settings(
        server={"debug": True},
        qdrant={"url": "http://localhost:6333", "collection": "test_lyrics"},
    )


@pytest.fixture
def mock_qdrant() -> MagicMock:
    """Mock Qdrant client."""
    mock = MagicMock()
    mock.get_collections.return_value = MagicMock(collections=[])
    return mock


@pytest.fixture
def test_app(test_settings, mock_qdrant) -> TestClient:
    """FastAPI test client with mocked dependencies."""
    app = create_app(settings=test_settings)
    # Override lifespan-created qdrant with mock
    app.state.qdrant = mock_qdrant
    return TestClient(app)
