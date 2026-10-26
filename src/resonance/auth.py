"""Short-lived caller sessions and signed Resonance JWTs."""

import base64
import hashlib
import hmac
import json
import secrets
import threading
import time
from dataclasses import dataclass, field

SESSION_TTL_SECONDS = 12 * 60 * 60
MAX_ACTIVE_SESSIONS = 128
MAX_RATE_LIMIT_BUCKETS = 4096
RATE_WINDOW_SECONDS = 5 * 60
MAX_FAILED_ATTEMPTS = 5


class SessionCapacityError(Exception):
    """The bounded in-memory session store has no free capacity."""


class RateLimitStorageError(Exception):
    """The bounded login rate limiter cannot track another client."""


class LoginRateLimitError(Exception):
    """A source IP has reached the failed-login threshold."""

    def __init__(self, retry_after: int) -> None:
        self.retry_after = retry_after


@dataclass(frozen=True)
class UserSession:
    session_id: str
    username: str
    password: str = field(repr=False)
    expires_at: int


@dataclass(frozen=True)
class Principal:
    username: str
    is_admin: bool
    session_id: str


class SessionStore:
    """Thread-safe, bounded, process-local storage for upstream credentials."""

    def __init__(self, *, ttl_seconds: int = SESSION_TTL_SECONDS, max_sessions: int = MAX_ACTIVE_SESSIONS) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_sessions = max_sessions
        self._sessions: dict[str, UserSession] = {}
        self._lock = threading.RLock()

    def create(self, username: str, password: str) -> UserSession:
        now = int(time.time())
        with self._lock:
            self._expire(now)
            if len(self._sessions) >= self.max_sessions:
                raise SessionCapacityError
            session = UserSession(secrets.token_urlsafe(24), username, password, now + self.ttl_seconds)
            self._sessions[session.session_id] = session
            return session

    def get(self, session_id: str) -> UserSession | None:
        now = int(time.time())
        with self._lock:
            session = self._sessions.get(session_id)
            if session is not None and session.expires_at <= now:
                self._sessions.pop(session_id, None)
                return None
            return session

    def revoke(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    def clear(self) -> None:
        with self._lock:
            self._sessions.clear()

    def _expire(self, now: int) -> None:
        for key, value in list(self._sessions.items()):
            if value.expires_at <= now:
                self._sessions.pop(key, None)


class FailedLoginLimiter:
    """Bounded per-source-IP rolling window for failed credential checks."""

    def __init__(
        self,
        *,
        window_seconds: int = RATE_WINDOW_SECONDS,
        maximum_failures: int = MAX_FAILED_ATTEMPTS,
    ) -> None:
        self.window_seconds = window_seconds
        self.maximum_failures = maximum_failures
        self._failures: dict[str, list[float]] = {}
        self._inflight: dict[str, int] = {}
        self._lock = threading.RLock()

    def begin(self, source: str, now: float | None = None) -> None:
        timestamp = time.monotonic() if now is None else now
        with self._lock:
            self._prune(timestamp)
            if source not in self._failures and source not in self._inflight:
                if len(self._failures) >= MAX_RATE_LIMIT_BUCKETS:
                    raise RateLimitStorageError
                self._failures[source] = []
            failures = self._failures.setdefault(source, [])
            inflight = self._inflight.get(source, 0)
            if len(failures) + inflight >= self.maximum_failures:
                retry_after = max(1, int(self.window_seconds - (timestamp - failures[0]))) if failures else 1
                raise LoginRateLimitError(retry_after)
            self._inflight[source] = inflight + 1

    def finish(self, source: str, *, success: bool, now: float | None = None) -> None:
        timestamp = time.monotonic() if now is None else now
        with self._lock:
            inflight = self._inflight.get(source, 0)
            if inflight > 1:
                self._inflight[source] = inflight - 1
            else:
                self._inflight.pop(source, None)
            failures = self._failures.setdefault(source, [])
            if not success:
                failures.append(timestamp)
            self._prune(timestamp)

    def _prune(self, now: float) -> None:
        for source, failures in list(self._failures.items()):
            active = [timestamp for timestamp in failures if now - timestamp < self.window_seconds]
            if active:
                self._failures[source] = active
            elif source not in self._inflight:
                self._failures.pop(source, None)


class AuthRuntime:
    """Runtime auth primitives; signing key and credentials never persist to disk."""

    def __init__(self, admin_user: str | None) -> None:
        self.admin_user = admin_user
        self.sessions = SessionStore()
        self.limiter = FailedLoginLimiter()
        self._signing_key = secrets.token_bytes(32)

    @staticmethod
    def _encode(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")

    @staticmethod
    def _decode(value: str) -> bytes:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))

    def issue(self, session: UserSession) -> str:
        now = int(time.time())
        header = {"alg": "HS256", "typ": "JWT"}
        claims = {
            "iss": "resonance",
            "aud": "resonance-api",
            "sub": session.username,
            "sid": session.session_id,
            "iat": now,
            "exp": session.expires_at,
        }
        header_json = json.dumps(header, separators=(",", ":")).encode()
        claims_json = json.dumps(claims, separators=(",", ":")).encode()
        content = f"{self._encode(header_json)}.{self._encode(claims_json)}"
        signature = hmac.new(self._signing_key, content.encode("ascii"), hashlib.sha256).digest()
        return f"{content}.{self._encode(signature)}"

    def decode(self, token: str) -> dict[str, object] | None:
        try:
            encoded_header, encoded_claims, encoded_signature = token.split(".")
            content = f"{encoded_header}.{encoded_claims}"
            expected = hmac.new(self._signing_key, content.encode("ascii"), hashlib.sha256).digest()
            if not hmac.compare_digest(self._decode(encoded_signature), expected):
                return None
            header = json.loads(self._decode(encoded_header))
            claims = json.loads(self._decode(encoded_claims))
            if not isinstance(header, dict) or header != {"alg": "HS256", "typ": "JWT"}:
                return None
            if not isinstance(claims, dict):
                return None
            now = int(time.time())
            if (
                set(claims) != {"iss", "aud", "sub", "sid", "iat", "exp"}
                or claims.get("iss") != "resonance"
                or claims.get("aud") != "resonance-api"
                or not isinstance(claims.get("sub"), str)
                or not isinstance(claims.get("sid"), str)
                or isinstance(claims.get("exp"), bool)
                or not isinstance(claims.get("exp"), int)
                or isinstance(claims.get("iat"), bool)
                or not isinstance(claims.get("iat"), int)
                or claims["iat"] > now
                or claims["exp"] <= claims["iat"]
                or claims["exp"] <= now
            ):
                return None
        except ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError:
            return None
        else:
            return claims

    def session_for_token(self, token: str) -> UserSession | None:
        """Resolve a bearer to its active Navidrome session."""
        claims = self.decode(token)
        if claims is None:
            return None
        session = self.sessions.get(str(claims["sid"]))
        if session is None or session.username != claims["sub"]:
            return None
        return session

    def principal(self, session: UserSession) -> Principal:
        return Principal(
            username=session.username,
            is_admin=bool(self.admin_user and session.username == self.admin_user),
            session_id=session.session_id,
        )
