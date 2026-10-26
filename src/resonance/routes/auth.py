"""Navidrome login, Resonance sessions, and caller-scoped dependencies."""

from collections.abc import Iterator
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, SecretStr, StringConstraints

from resonance.auth import (
    SESSION_TTL_SECONDS,
    AuthRuntime,
    LoginRateLimitError,
    Principal,
    RateLimitStorageError,
    SessionCapacityError,
    UserSession,
)
from resonance.errors import ApplicationError, NavidromeRejectedError
from resonance.navidrome import NavidromeClient, NavidromeCredentials

router = APIRouter(prefix="/api/auth", tags=["auth"])
COOKIE_NAME = "resonance_session"
COOKIE_PATH = "/api"
LOCAL_HOSTS = {"localhost", "127.0.0.1"}
LOCAL_ORIGINS = {
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
}


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: Annotated[str, StringConstraints(min_length=1, max_length=256)]
    password: SecretStr


def _auth_runtime(request: Request) -> AuthRuntime:
    runtime = getattr(request.app.state, "auth_runtime", None)
    if runtime is None:
        raise HTTPException(status_code=503, detail="Authentication is unavailable")
    return runtime


def _source_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _origin(request: Request) -> str | None:
    value = request.headers.get("origin")
    if not value:
        return None
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path not in {"", "/"}:
        return "invalid"
    return f"{parsed.scheme}://{parsed.netloc}"


def _request_host(request: Request) -> str:
    return (request.url.hostname or "").lower()


def check_auth_transport(request: Request, *, require_origin: bool = False) -> None:
    origin = _origin(request)
    settings = request.app.state.settings
    host = _request_host(request)
    if request.url.scheme == "https":
        if require_origin and (origin is None or origin != f"https://{request.url.netloc}"):
            raise HTTPException(status_code=403, detail="Request origin is not allowed")
        if origin and origin != f"https://{request.url.netloc}":
            raise HTTPException(status_code=403, detail="Request origin is not allowed")
        return

    if not settings.debug or host not in LOCAL_HOSTS:
        raise HTTPException(status_code=400, detail="HTTPS is required")
    if origin is not None and origin not in LOCAL_ORIGINS:
        raise HTTPException(status_code=403, detail="Request origin is not allowed")
    if require_origin and origin not in LOCAL_ORIGINS:
        raise HTTPException(status_code=403, detail="Request origin is not allowed")


def _limiter_begin(runtime: AuthRuntime, request: Request) -> str:
    source = _source_ip(request)
    try:
        runtime.limiter.begin(source)
    except LoginRateLimitError as error:
        raise HTTPException(
            status_code=429,
            detail="Too many failed login attempts",
            headers={"Retry-After": str(error.retry_after)},
        ) from None
    except RateLimitStorageError:
        raise HTTPException(
            status_code=503,
            detail="Login rate limiter is full",
            headers={"Retry-After": "60"},
        ) from None
    return source


def _create_session(runtime: AuthRuntime, username: str, password: str) -> UserSession:
    try:
        return runtime.sessions.create(username, password)
    except SessionCapacityError:
        raise HTTPException(
            status_code=503,
            detail="Authentication session capacity reached",
            headers={"Retry-After": "60"},
        ) from None


def _validated_login(
    request: Request,
    body: LoginRequest,
    *,
    require_origin: bool,
) -> tuple[UserSession, list[dict[str, str]]]:
    check_auth_transport(request, require_origin=require_origin)
    runtime = _auth_runtime(request)
    source = _limiter_begin(runtime, request)
    try:
        client = NavidromeClient(
            request.app.state.settings.navidrome,
            NavidromeCredentials(body.username, body.password.get_secret_value()),
        )
    except ApplicationError:
        runtime.limiter.finish(source, success=True)
        raise
    try:
        libraries = client.libraries()
    except NavidromeRejectedError:
        runtime.limiter.finish(source, success=False)
        raise HTTPException(status_code=401, detail="Invalid Navidrome credentials") from None
    except ApplicationError:
        runtime.limiter.finish(source, success=True)
        raise
    finally:
        client.close()
    runtime.limiter.finish(source, success=True)
    session = _create_session(runtime, body.username, body.password.get_secret_value())
    return session, [{"id": library.id, "name": library.name} for library in libraries]


def _user_response(runtime: AuthRuntime, session: UserSession, libraries: list[dict[str, str]]) -> dict:
    principal = runtime.principal(session)
    return {"username": principal.username, "is_admin": principal.is_admin, "libraries": libraries}


def _set_cookie(response: Response, request: Request, token: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
        path=COOKIE_PATH,
    )


def _session_for_request(
    request: Request,
    authorization: str | None,
    *,
    enforce_cookie_origin: bool = True,
) -> tuple[UserSession, bool]:
    cookie_token = request.cookies.get(COOKIE_NAME)
    bearer_token = None
    if authorization is not None:
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() != "bearer" or not value.strip():
            raise HTTPException(status_code=401, detail="Authentication required")
        bearer_token = value.strip()
    token = bearer_token or cookie_token
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"})
    if bearer_token:
        check_auth_transport(request)
    else:
        check_origin = enforce_cookie_origin and request.method not in {"GET", "HEAD", "OPTIONS"}
        check_auth_transport(request, require_origin=check_origin)
    runtime = _auth_runtime(request)
    session = runtime.session_for_token(token)
    if session is None:
        raise HTTPException(status_code=401, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"})
    return session, bearer_token is not None


def get_user_session(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> UserSession:
    session, _ = _session_for_request(request, authorization)
    return session


def get_principal(session: Annotated[UserSession, Depends(get_user_session)], request: Request) -> Principal:
    return _auth_runtime(request).principal(session)


def require_admin(principal: Annotated[Principal, Depends(get_principal)]) -> Principal:
    if not principal.is_admin:
        raise HTTPException(status_code=403, detail="Administrator access required")
    return principal


def get_navidrome(
    request: Request,
    session: Annotated[UserSession, Depends(get_user_session)],
) -> Iterator[NavidromeClient]:
    injected = getattr(request.app.state, "navidrome", None)
    if injected is not None:
        yield injected
        return
    client = NavidromeClient(
        request.app.state.settings.navidrome,
        NavidromeCredentials(session.username, session.password),
    )
    try:
        yield client
    finally:
        client.close()


@router.post("/login")
def login(body: LoginRequest, request: Request, response: Response) -> dict:
    session, libraries = _validated_login(request, body, require_origin=True)
    token = _auth_runtime(request).issue(session)
    _set_cookie(response, request, token)
    return _user_response(_auth_runtime(request), session, libraries)


@router.post("/token")
def token(body: LoginRequest, request: Request) -> dict:
    check_auth_transport(request)
    session, _libraries = _validated_login(request, body, require_origin=False)
    runtime = _auth_runtime(request)
    return {"access_token": runtime.issue(session), "token_type": "bearer", "expires_in": SESSION_TTL_SECONDS}


@router.get("/me")
def me(
    request: Request,
    session: Annotated[UserSession, Depends(get_user_session)],
    source: Annotated[NavidromeClient, Depends(get_navidrome)],
) -> dict:
    libraries = [{"id": library.id, "name": library.name} for library in source.libraries()]
    return _user_response(_auth_runtime(request), session, libraries)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, authorization: Annotated[str | None, Header()] = None) -> Response:
    check_auth_transport(request)
    cookie_token = request.cookies.get(COOKIE_NAME)
    token_value = None
    if authorization:
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() != "bearer" or not value.strip():
            raise HTTPException(status_code=401, detail="Authentication required")
        token_value = value.strip()
    else:
        if cookie_token:
            check_auth_transport(request, require_origin=True)
        token_value = cookie_token
    if token_value:
        runtime = _auth_runtime(request)
        claims = runtime.decode(token_value)
        if claims and isinstance(claims.get("sid"), str):
            runtime.sessions.revoke(claims["sid"])
    response.delete_cookie(
        COOKIE_NAME,
        path=COOKIE_PATH,
        secure=request.url.scheme == "https",
        httponly=True,
        samesite="lax",
    )
    response.status_code = 204
    return response
