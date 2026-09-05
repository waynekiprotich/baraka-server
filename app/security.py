"""Response hardening, the cache boundary, transport compression, and auth.

Everything here is registered centrally in create_app(). No endpoint sets its
own security headers, cache-control or content-encoding.
"""

from __future__ import annotations

import functools
import gzip
import hashlib
import uuid

from flask import current_app, g, request
from flask_jwt_extended import get_jwt, get_jwt_identity, verify_jwt_in_request
from sqlalchemy import select

from .errors import (
    CODE_INVALID_TOKEN,
    CODE_TOKEN_EXPIRED,
    CODE_TOKEN_REVOKED,
    ForbiddenError,
    UnauthorizedError,
    error_response,
)
from .extensions import db
from .models import AdminUser, TokenBlocklist

CSP = (
    "default-src 'none'; "
    "img-src 'self' data:; "
    "style-src 'self' 'unsafe-inline'; "
    "script-src 'self'; "
    "connect-src 'self'; "
    "font-src 'self'; "
    "base-uri 'none'; "
    "form-action 'none'; "
    "frame-ancestors 'none'"
)

PERMISSIONS_POLICY = (
    "accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), "
    "microphone=(), payment=(), usb=()"
)

# Paths whose responses must never be stored by a shared or private cache.
PRIVATE_PREFIXES = ("/api/v1/admin", "/api/v1/auth")

# Public catalog reads that may be cached and revalidated.
PUBLIC_CACHEABLE_PREFIXES = (
    "/api/v1/settings",
    "/api/v1/news",
    "/api/v1/events",
    "/api/v1/gallery",
)

COMPRESSIBLE_TYPES = ("application/json", "text/", "application/javascript", "image/svg+xml")


# --- client identity ------------------------------------------------------


def client_ip() -> str:
    """The caller's address, trusting exactly as many proxies as configured."""
    hops = current_app.config.get("TRUSTED_PROXY_HOPS", 0)
    if hops:
        forwarded = request.headers.get("X-Forwarded-For", "")
        parts = [part.strip() for part in forwarded.split(",") if part.strip()]
        if parts:
            # The last `hops` entries were appended by our own proxies; the one
            # immediately before them is the address they saw.
            index = max(0, len(parts) - hops)
            return parts[index]
    return request.remote_addr or "0.0.0.0"


def hash_ip(address: str) -> str:
    salt = current_app.config.get("IP_HASH_SALT", "")
    return hashlib.sha256(f"{salt}:{address}".encode()).hexdigest()


# --- request/response pipeline -------------------------------------------


def register_security(app) -> None:
    @app.before_request
    def _assign_request_id():
        # Reuse an inbound id so an upstream proxy's logs and ours name the
        # same request.
        g.request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex[:16]

    @app.after_request
    def _finalise(response):
        response.headers.setdefault("X-Request-Id", getattr(g, "request_id", "-"))
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Permissions-Policy"] = PERMISSIONS_POLICY
        response.headers.setdefault("Content-Security-Policy", CSP)

        _apply_cache_policy(response)
        response = _apply_etag(response)
        return _apply_gzip(response)


def _apply_cache_policy(response) -> None:
    path = request.path
    if any(path.startswith(prefix) for prefix in PRIVATE_PREFIXES):
        # The privacy boundary: admin and auth responses are never stored.
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        return
    if "Cache-Control" in response.headers:
        return
    if (
        request.method == "GET"
        and response.status_code == 200
        and any(path.startswith(prefix) for prefix in PUBLIC_CACHEABLE_PREFIXES)
    ):
        response.headers["Cache-Control"] = current_app.config["PUBLIC_CACHE_CONTROL"]
        return
    response.headers["Cache-Control"] = "no-store"


def _apply_etag(response):
    if request.method not in ("GET", "HEAD"):
        return response
    if response.status_code != 200 or response.direct_passthrough:
        return response
    cache_control = response.headers.get("Cache-Control", "")
    if "no-store" in cache_control:
        return response
    if "ETag" not in response.headers:
        digest = hashlib.md5(response.get_data(), usedforsecurity=False).hexdigest()
        # Weak, because the byte representation varies with Content-Encoding.
        response.headers["ETag"] = f'W/"{digest}"'
    if_none_match = request.headers.get("If-None-Match", "")
    candidates = {tag.strip() for tag in if_none_match.split(",") if tag.strip()}
    if response.headers["ETag"] in candidates:
        response.status_code = 304
        response.set_data(b"")
        response.headers.pop("Content-Type", None)
    return response


def _apply_gzip(response):
    if response.status_code == 304 or response.direct_passthrough:
        return response
    if response.headers.get("Content-Encoding"):
        return response
    accepted = request.headers.get("Accept-Encoding", "")
    content_type = response.headers.get("Content-Type", "")
    if "gzip" not in accepted.lower():
        response.headers.add("Vary", "Accept-Encoding")
        return response
    if not any(content_type.startswith(kind) for kind in COMPRESSIBLE_TYPES):
        return response
    body = response.get_data()
    if len(body) < current_app.config["GZIP_MIN_BYTES"]:
        response.headers.add("Vary", "Accept-Encoding")
        return response
    compressed = gzip.compress(body, compresslevel=6)
    response.set_data(compressed)
    response.headers["Content-Encoding"] = "gzip"
    response.headers["Content-Length"] = str(len(compressed))
    response.headers.add("Vary", "Accept-Encoding")
    return response


# --- JWT plumbing ---------------------------------------------------------


def register_jwt_callbacks(jwt) -> None:
    @jwt.token_in_blocklist_loader
    def _is_revoked(_jwt_header, jwt_payload):
        jti = jwt_payload.get("jti")
        if not jti:
            return True
        stmt = select(TokenBlocklist.id).where(TokenBlocklist.jti == jti).limit(1)
        return db.session.execute(stmt).first() is not None

    @jwt.expired_token_loader
    def _expired(_header, _payload):
        return error_response(
            {"error": {"code": CODE_TOKEN_EXPIRED, "message": "Your session has expired."}}, 401
        )

    @jwt.revoked_token_loader
    def _revoked(_header, _payload):
        return error_response(
            {"error": {"code": CODE_TOKEN_REVOKED, "message": "This token has been revoked."}}, 401
        )

    @jwt.invalid_token_loader
    def _invalid(_reason):
        return error_response(
            {"error": {"code": CODE_INVALID_TOKEN, "message": "This token is not valid."}}, 401
        )

    @jwt.unauthorized_loader
    def _missing(_reason):
        return error_response(
            {
                "error": {
                    "code": CODE_INVALID_TOKEN,
                    "message": "An access token is required.",
                }
            },
            401,
        )

    @jwt.needs_fresh_token_loader
    def _needs_fresh(_header, _payload):
        return error_response(
            {"error": {"code": CODE_INVALID_TOKEN, "message": "A fresh token is required."}}, 401
        )


def current_admin() -> AdminUser:
    """The admin the request is authenticated as. Requires @admin_required()."""
    admin = getattr(g, "admin_user", None)
    if admin is None:
        raise UnauthorizedError()
    return admin


def load_admin_from_token() -> AdminUser:
    identity = get_jwt_identity()
    try:
        admin_id = int(identity)
    except (TypeError, ValueError):
        raise UnauthorizedError("This token is not valid.", code=CODE_INVALID_TOKEN) from None
    admin = db.session.get(AdminUser, admin_id)
    if admin is None:
        # The account was deleted while the token was still inside its window.
        raise UnauthorizedError("This token is not valid.", code=CODE_INVALID_TOKEN)
    if not admin.is_active:
        # A deactivated admin stops working now, not when the token lapses.
        raise ForbiddenError("This account has been deactivated.")
    return admin


def admin_required(*, refresh: bool = False):
    """Every admin route uses this. It loads the account and checks is_active.

    A bare @jwt_required() would only prove the token is unexpired; it never
    looks at the database, so a deactivated admin would keep working until
    their token lapsed.
    """

    def decorator(view):
        @functools.wraps(view)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request(refresh=refresh)
            claims = get_jwt()
            expected = "refresh" if refresh else "access"
            if claims.get("type") != expected:
                raise UnauthorizedError(
                    "This token is not valid for this endpoint.", code=CODE_INVALID_TOKEN
                )
            g.admin_user = load_admin_from_token()
            return view(*args, **kwargs)

        return wrapper

    return decorator
