"""Error handling.

Every error returned to the client uses one shape so the frontend's
`ApiError` can parse it uniformly: { code, message, details? }.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

_logger = logging.getLogger("manhwamaniacs.errors")


class AppError(Exception):
    """Raised by services/routes for expected, client-facing failures."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "app_error",
        status_code: int = 400,
        details: object | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details


def _envelope(status_code: int, code: str, message: str, details: object | None = None):
    body: dict = {"code": code, "message": message}
    if details is not None:
        body["details"] = details
    return JSONResponse(status_code=status_code, content=body)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError):
        return _envelope(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError):
        return _envelope(422, "validation_error", "Invalid request.", exc.errors())

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException):
        return _envelope(exc.status_code, "http_error", str(exc.detail))

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception):
        # Log the full traceback server-side for debugging, but never leak
        # internals to the client — they only get a generic message.
        _logger.exception(
            "Unhandled error on %s %s", request.method, request.url.path
        )
        return _envelope(500, "internal_error", "An unexpected error occurred.")
