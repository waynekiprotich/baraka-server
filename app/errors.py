"""The error envelope and the handlers that guarantee it.

Every non-2xx response leaving this application carries exactly:

    {"error": {"code": "...", "message": "...", "fields": {...}}}

`fields` is present only for validation failures. A 500 carries a `reference`
instead -- an id that appears in the logs beside the traceback -- and nothing
that describes the failure.
"""

from __future__ import annotations

import logging
import uuid

from flask import jsonify, request
from werkzeug.exceptions import HTTPException

logger = logging.getLogger(__name__)

# Every code the API is allowed to emit (SPEC section 5).
CODE_VALIDATION_ERROR = "VALIDATION_ERROR"
CODE_NOT_FOUND = "NOT_FOUND"
CODE_UNAUTHORIZED = "UNAUTHORIZED"
CODE_INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
CODE_TOKEN_EXPIRED = "TOKEN_EXPIRED"
CODE_TOKEN_REVOKED = "TOKEN_REVOKED"
CODE_INVALID_TOKEN = "INVALID_TOKEN"
CODE_FORBIDDEN = "FORBIDDEN"
CODE_RATE_LIMITED = "RATE_LIMITED"
CODE_CONFLICT = "CONFLICT"
CODE_PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
CODE_UNSUPPORTED_MEDIA_TYPE = "UNSUPPORTED_MEDIA_TYPE"
CODE_INTERNAL_ERROR = "INTERNAL_ERROR"

_STATUS_CODES = {
    400: CODE_VALIDATION_ERROR,
    401: CODE_UNAUTHORIZED,
    403: CODE_FORBIDDEN,
    404: CODE_NOT_FOUND,
    405: CODE_NOT_FOUND,
    409: CODE_CONFLICT,
    413: CODE_PAYLOAD_TOO_LARGE,
    415: CODE_UNSUPPORTED_MEDIA_TYPE,
    422: CODE_VALIDATION_ERROR,
    429: CODE_RATE_LIMITED,
}

_STATUS_MESSAGES = {
    400: "The request could not be understood.",
    401: "Authentication is required.",
    403: "You do not have permission to do that.",
    404: "The requested resource does not exist.",
    405: "That method is not available for this resource.",
    409: "That change conflicts with existing data.",
    413: "The request body is too large.",
    415: "That media type is not supported.",
    422: "The request could not be processed.",
    429: "Too many requests. Please try again later.",
}


class ApiError(Exception):
    """An error that should be rendered as the standard envelope."""

    status = 400
    code = CODE_VALIDATION_ERROR
    message = "The request could not be understood."

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        status: int | None = None,
        fields: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message or self.message)
        if message is not None:
            self.message = message
        if code is not None:
            self.code = code
        if status is not None:
            self.status = status
        self.fields = fields or None
        self.headers = headers or {}

    def to_payload(self) -> dict:
        error: dict[str, object] = {"code": self.code, "message": self.message}
        if self.fields:
            error["fields"] = self.fields
        return {"error": error}


class ValidationError(ApiError):
    status = 400
    code = CODE_VALIDATION_ERROR
    message = "Some fields need attention."


class NotFoundError(ApiError):
    status = 404
    code = CODE_NOT_FOUND
    message = "The requested resource does not exist."


class UnauthorizedError(ApiError):
    status = 401
    code = CODE_UNAUTHORIZED
    message = "Authentication is required."


class InvalidCredentialsError(ApiError):
    status = 401
    code = CODE_INVALID_CREDENTIALS
    message = "Email or password is incorrect."


class ForbiddenError(ApiError):
    status = 403
    code = CODE_FORBIDDEN
    message = "You do not have permission to do that."


class ConflictError(ApiError):
    status = 409
    code = CODE_CONFLICT
    message = "That change conflicts with existing data."


class RateLimitedError(ApiError):
    status = 429
    code = CODE_RATE_LIMITED
    message = "Too many requests. Please try again later."


class PayloadTooLargeError(ApiError):
    status = 413
    code = CODE_PAYLOAD_TOO_LARGE
    message = "That file is too large."


class UnsupportedMediaTypeError(ApiError):
    status = 415
    code = CODE_UNSUPPORTED_MEDIA_TYPE
    message = "That media type is not supported."


def error_response(payload: dict, status: int, headers: dict[str, str] | None = None):
    response = jsonify(payload)
    response.status_code = status
    for key, value in (headers or {}).items():
        response.headers[key] = value
    return response


def register_error_handlers(app) -> None:
    @app.errorhandler(ApiError)
    def _handle_api_error(exc: ApiError):
        return error_response(exc.to_payload(), exc.status, exc.headers)

    @app.errorhandler(HTTPException)
    def _handle_http_error(exc: HTTPException):
        status = exc.code or 500
        if status >= 500:
            return _handle_unexpected(exc)
        payload = {
            "error": {
                "code": _STATUS_CODES.get(status, CODE_VALIDATION_ERROR),
                "message": _STATUS_MESSAGES.get(status, "The request could not be completed."),
            }
        }
        return error_response(payload, status)

    @app.errorhandler(Exception)
    def _handle_unexpected(exc: Exception):
        reference = uuid.uuid4().hex[:16]
        logger.exception(
            "Unhandled error reference=%s method=%s path=%s",
            reference,
            request.method if request else "-",
            request.path if request else "-",
            exc_info=exc,
        )
        payload = {
            "error": {
                "code": CODE_INTERNAL_ERROR,
                "message": "Something went wrong on our end.",
                "reference": reference,
            }
        }
        return error_response(payload, 500)
