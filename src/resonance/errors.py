"""Transport-independent, safe application failures."""

from collections.abc import Callable
from functools import wraps
from typing import NoReturn


class ApplicationError(Exception):
    """An error whose message is safe to return without upstream response bodies."""

    def __init__(self, message: str, *, code: str = "invalid_request", status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


class NavidromeRejectedError(ApplicationError):
    """An explicit failed Subsonic envelope, rather than an uncertain HTTP outcome."""

    def __init__(self, error_code: int) -> None:
        super().__init__("Navidrome rejected the request", code="navidrome_rejected", status=502)
        self.error_code = error_code


def fail(message: str, *, code: str = "invalid_request", status: int = 400) -> NoReturn:
    """Raise a safe domain error from shared policy code."""
    raise ApplicationError(message, code=code, status=status) from None


def external_errors[**P, R](message: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Sanitize unforeseen SDK failures at application boundaries."""

    def decorate(function: Callable[P, R]) -> Callable[P, R]:
        @wraps(function)
        def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
            try:
                return function(*args, **kwargs)
            except ApplicationError:
                raise
            except Exception:  # noqa: BLE001 -- safe application boundary
                fail(message, code="dependency_unavailable", status=502)

        return wrapped

    return decorate
