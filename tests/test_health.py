"""Tests for health endpoint."""


class TestHealthEndpoint:
    def test_healthy_when_qdrant_connected(self, test_app, mock_qdrant):
        response = test_app.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["qdrant"] == "connected"
        assert data["provider"] == "openai"

    def test_unhealthy_when_qdrant_unreachable(self, test_app, mock_qdrant):
        mock_qdrant.get_collections.side_effect = ConnectionError("refused")
        response = test_app.get("/health")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["qdrant"] == "unreachable"


class TestSwaggerUI:
    def test_docs_available_in_debug_mode(self, test_app):
        response = test_app.get("/docs")
        assert response.status_code == 200

    def test_docs_disabled_when_not_debug(self):
        from resonance.app import create_app
        from resonance.config import Settings

        settings = Settings(server={"debug": False})
        app = create_app(settings=settings)
        client = __import__("fastapi.testclient", fromlist=["TestClient"]).TestClient(app)
        app.state.qdrant = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()
        response = client.get("/docs")
        assert response.status_code == 404
