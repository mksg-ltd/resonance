"""HTTP login/session route behavior with a small Navidrome test double."""

import time

from fastapi.testclient import TestClient

from resonance.app import create_app
from resonance.config import Settings
from resonance.errors import NavidromeRejectedError
from resonance.models import Library

WRONG_PASSWORD = "wrong-password"  # noqa: S105 -- intentional auth fixture


class LoginSource:
    def __init__(self, _config, credentials):
        self.credentials = credentials
        self.closed = False

    def libraries(self):
        if self.credentials.password == WRONG_PASSWORD:
            raise NavidromeRejectedError(40)
        return [Library("library-a", "Library A")]

    def close(self):
        self.closed = True


def app_for(monkeypatch, *, debug=True, admin_user="owner"):
    monkeypatch.setattr("resonance.routes.auth.NavidromeClient", LoginSource)
    settings = Settings(
        debug=debug,
        admin_user=admin_user,
        navidrome={"base_url": "https://music.test"},
        _env_file=None,
    )
    return create_app(settings)


def test_browser_login_sets_http_only_cookie_without_exposing_token(monkeypatch):
    app = app_for(monkeypatch, debug=False)
    with TestClient(app, base_url="https://resonance.test") as client:
        response = client.post(
            "/api/auth/login",
            json={"username": "owner", "password": "correct-password"},
            headers={"Origin": "https://resonance.test"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "username": "owner",
        "is_admin": True,
        "libraries": [{"id": "library-a", "name": "Library A"}],
    }
    assert "access_token" not in response.json()
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "secure" in cookie
    assert "samesite=lax" in cookie
    assert "path=/api" in cookie


def test_login_errors_are_generic_and_token_and_cookie_routes_share_rate_limit(monkeypatch):
    app = app_for(monkeypatch)
    with TestClient(app, base_url="http://localhost:8000") as client:
        failures = []
        for attempt in range(5):
            path = "/api/auth/login" if attempt % 2 == 0 else "/api/auth/token"
            headers = {"Origin": "http://localhost:8000"} if path.endswith("login") else {}
            response = client.post(
                path,
                json={"username": "unknown-user", "password": "wrong-password"},
                headers=headers,
            )
            failures.append(response)
        limited = client.post(
            "/api/auth/token",
            json={"username": "unknown-user", "password": "wrong-password"},
        )

    assert all(response.status_code == 401 for response in failures)
    assert all(response.json()["detail"] == "Invalid Navidrome credentials" for response in failures)
    assert all("unknown-user" not in response.text and WRONG_PASSWORD not in response.text for response in failures)
    assert all("set-cookie" not in response.headers for response in failures)
    assert limited.status_code == 429
    assert int(limited.headers["retry-after"]) > 0
    assert app.state.auth_runtime.sessions._sessions == {}


def test_remote_plain_http_is_rejected_for_login_and_protected_bearer_calls(monkeypatch):
    app = app_for(monkeypatch, debug=False)
    session = app.state.auth_runtime.sessions.create("owner", "private-password")
    bearer = app.state.auth_runtime.issue(session)
    with TestClient(app, base_url="http://remote.test") as client:
        login = client.post(
            "/api/auth/login",
            json={"username": "owner", "password": "correct-password"},
            headers={"Origin": "http://remote.test"},
        )
        protected = client.get("/api/config", headers={"Authorization": f"Bearer {bearer}"})
        assert app.state.auth_runtime.sessions.get(session.session_id) == session

    assert login.status_code == 400
    assert protected.status_code == 400


def test_session_capacity_returns_retry_after_without_replacing_sessions(monkeypatch):
    app = app_for(monkeypatch)
    active = app.state.auth_runtime.sessions.create("existing", "private-password")
    app.state.auth_runtime.sessions.max_sessions = 1
    with TestClient(app, base_url="http://localhost:8000") as client:
        response = client.post(
            "/api/auth/login",
            json={"username": "owner", "password": "correct-password"},
            headers={"Origin": "http://localhost:8000"},
        )
        assert app.state.auth_runtime.sessions.get(active.session_id) == active

    assert response.status_code == 503
    assert int(response.headers["retry-after"]) > 0


def test_rate_limiter_saturation_fails_closed_with_retry_after(monkeypatch):
    app = app_for(monkeypatch)
    now = time.monotonic()
    app.state.auth_runtime.limiter._failures = {f"ip-{index}": [now] for index in range(4096)}
    with TestClient(app, base_url="http://localhost:8000") as client:
        response = client.post(
            "/api/auth/token",
            json={"username": "owner", "password": "correct-password"},
        )

    assert response.status_code == 503
    assert int(response.headers["retry-after"]) > 0
    assert app.state.auth_runtime.sessions._sessions == {}
