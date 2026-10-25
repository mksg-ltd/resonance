"""Authentication primitive tests independent of the ASGI threadpool."""

import pytest

from resonance.auth import (
    AuthRuntime,
    FailedLoginLimiter,
    LoginRateLimitError,
    RateLimitStorageError,
    SessionCapacityError,
    SessionStore,
)


def test_jwt_rejects_tampering_and_store_rejects_expired_or_full_sessions(monkeypatch: pytest.MonkeyPatch) -> None:
    now = 1_800_000_000
    monkeypatch.setattr("resonance.auth.time.time", lambda: now)
    store = SessionStore(ttl_seconds=60, max_sessions=1)
    session = store.create("alice", "secret")
    runtime = AuthRuntime("alice")
    token = runtime.issue(session)

    assert runtime.decode(token)["sub"] == "alice"
    assert "secret" not in token
    assert set(runtime.decode(token)) == {"iss", "aud", "sub", "sid", "iat", "exp"}
    assert runtime.principal(session).is_admin
    assert store.get(session.session_id) == session
    with pytest.raises(SessionCapacityError):
        store.create("bob", "secret")

    header, claims, signature = token.split(".")
    changed_signature = ("A" if signature[0] != "A" else "B") + signature[1:]
    assert runtime.decode(f"{header}.{claims}.{changed_signature}") is None
    store.revoke(session.session_id)
    assert store.get(session.session_id) is None
    expired = store.create("bob", "secret")
    now += 61
    assert store.get(expired.session_id) is None


def test_default_session_capacity_is_128_without_eviction():
    store = SessionStore()
    sessions = [store.create(f"user-{index}", "secret") for index in range(128)]

    with pytest.raises(SessionCapacityError):
        store.create("overflow", "secret")

    assert all(store.get(session.session_id) == session for session in sessions)


def test_failed_login_limiter_expires_and_caps_buckets() -> None:
    limiter = FailedLoginLimiter(window_seconds=10, maximum_failures=2)
    limiter.begin("127.0.0.1", now=1)
    limiter.finish("127.0.0.1", success=False, now=1)
    limiter.begin("127.0.0.1", now=2)
    limiter.finish("127.0.0.1", success=False, now=2)
    with pytest.raises(LoginRateLimitError):
        limiter.begin("127.0.0.1", now=3)
    limiter.begin("127.0.0.1", now=12)
    limiter.finish("127.0.0.1", success=True, now=12)

    bounded = FailedLoginLimiter()
    for number in range(4096):
        bounded.begin(str(number), now=1)
        bounded.finish(str(number), success=False, now=1)
    with pytest.raises(RateLimitStorageError):
        bounded.begin("overflow", now=2)
