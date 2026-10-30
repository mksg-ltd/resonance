"""Transport-independent, safe application failures."""

import logging
from collections.abc import Callable
from functools import wraps
from pathlib import Path
from traceback import extract_tb
from typing import NoReturn

logger = logging.getLogger("uvicorn.error.resonance.errors")


class ApplicationError(Exception):
    """An error whose message is safe to return without upstream response bodies."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "invalid_request",
        status: int = 400,
        diagnostic: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status = status
        self.diagnostic = diagnostic


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
            except Exception as error:  # noqa: BLE001 -- safe application boundary
                frames = extract_tb(error.__traceback__)
                location = " <- ".join(
                    f"{Path(frame.filename).name}:{frame.lineno}:{frame.name}" for frame in frames[-4:]
                )
                logger.warning(
                    "Unexpected dependency error in %s: exception_type=%s location=%s",
                    function.__qualname__,
                    type(error).__name__,
                    location or "unknown",
                )
                fail(message, code="dependency_unavailable", status=502)

        return wrapped

    return decorate
