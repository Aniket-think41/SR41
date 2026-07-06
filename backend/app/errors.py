"""
Error envelope (BACKEND_SPEC §7):
  { "error": { "code": "...", "message": "...", "status": 404 } }
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status = status
        self.code = code
        self.message = message


def not_found(what: str) -> ApiError:
    return ApiError(404, "NOT_FOUND", f"{what} not found")


def forbidden(message: str) -> ApiError:
    return ApiError(403, "FORBIDDEN", message)


def unauthorized(message: str = "Authentication required") -> ApiError:
    return ApiError(401, "UNAUTHORIZED", message)


def conflict(message: str) -> ApiError:
    return ApiError(409, "CONFLICT", message)


def validation(message: str) -> ApiError:
    return ApiError(422, "VALIDATION_ERROR", message)


def payment_required(message: str) -> ApiError:
    """402 — the action is blocked by the entity's plan/quota (spec §2)."""
    return ApiError(402, "PAYMENT_REQUIRED", message)


def service_unavailable(message: str) -> ApiError:
    """503 — a feature is scaffolded but not yet configured (e.g. payments)."""
    return ApiError(503, "SERVICE_UNAVAILABLE", message)


def envelope(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message, "status": status}})


def install_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error_handler(_: Request, exc: ApiError):
        return envelope(exc.status, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        loc = ".".join(str(x) for x in first.get("loc", []) if x != "body")
        msg = f"{loc}: {first.get('msg', 'invalid request')}" if loc else first.get("msg", "Invalid request")
        return envelope(422, "VALIDATION_ERROR", msg)

    @app.exception_handler(StarletteHTTPException)
    async def http_handler(_: Request, exc: StarletteHTTPException):
        code = {401: "UNAUTHORIZED", 402: "PAYMENT_REQUIRED", 403: "FORBIDDEN", 404: "NOT_FOUND", 409: "CONFLICT", 422: "VALIDATION_ERROR", 503: "SERVICE_UNAVAILABLE"}.get(
            exc.status_code, "INTERNAL_ERROR"
        )
        return envelope(exc.status_code, code, str(exc.detail))

    @app.exception_handler(Exception)
    async def fallback_handler(_: Request, exc: Exception):  # pragma: no cover
        return envelope(500, "INTERNAL_ERROR", "Something went wrong")
