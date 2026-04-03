from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from starlette import status

from app.core.request_context import get_request_id

logger = logging.getLogger(__name__)


def error_envelope(
    *,
    code: str,
    message: str,
    detail: Any,
    request_id: str | None,
) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "request_id": request_id,
            "detail": detail,
        }
    }


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RateLimitExceeded)
    async def handle_rate_limit_exceeded(_: Request, exc: RateLimitExceeded) -> JSONResponse:
        rid = get_request_id()
        detail = exc.detail
        message = detail if isinstance(detail, str) else "Rate limit exceeded"
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content=error_envelope(
                code="rate_limit_exceeded",
                message=message,
                detail=detail,
                request_id=rid,
            ),
        )

    @app.exception_handler(HTTPException)
    async def handle_http_exception(_: Request, exc: HTTPException) -> JSONResponse:
        rid = get_request_id()
        detail = exc.detail
        message = detail if isinstance(detail, str) else "Request failed"
        return JSONResponse(
            status_code=exc.status_code,
            content=error_envelope(
                code=f"http_{exc.status_code}",
                message=message,
                detail=detail,
                request_id=rid,
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_exception(_: Request, exc: RequestValidationError) -> JSONResponse:
        rid = get_request_id()
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=error_envelope(
                code="validation_error",
                message="Validation error",
                detail=exc.errors(),
                request_id=rid,
            ),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_exception(_: Request, exc: Exception) -> JSONResponse:
        rid = get_request_id()
        logger.exception("Unexpected error (request_id=%s)", rid, exc_info=exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_envelope(
                code="internal_error",
                message="Unexpected server error",
                detail="Unexpected server error",
                request_id=rid,
            ),
        )
