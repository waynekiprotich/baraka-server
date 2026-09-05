"""Supabase Storage client for uploaded images.

Talks to the Storage REST API directly over `urllib` rather than pulling in the
`supabase` SDK -- three small HTTP calls do not justify a new dependency. The
service-role key used here never leaves the server: it is read from the
environment and only ever attached to server-to-Supabase requests, never
returned to a client or shipped to the frontend.
"""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request

import certifi
from flask import current_app

from ..errors import ValidationError

# A pinned CA bundle rather than the platform default: some local Python
# installs (notably python.org builds on macOS) ship with no system trust
# store wired up for `urllib`, which would otherwise fail every HTTPS call
# with CERTIFICATE_VERIFY_FAILED regardless of the network being fine.
_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())


class SupabaseStorageError(RuntimeError):
    """The Storage API rejected a request or was unreachable."""


def _config() -> tuple[str, str, str]:
    url = current_app.config.get("SUPABASE_URL")
    key = current_app.config.get("SUPABASE_SERVICE_ROLE_KEY")
    bucket = current_app.config.get("SUPABASE_STORAGE_BUCKET")
    if not url or not key or not bucket:
        raise SupabaseStorageError(
            "Supabase Storage is not configured (SUPABASE_URL / "
            "SUPABASE_SERVICE_ROLE_KEY / SUPABASE_STORAGE_BUCKET)."
        )
    return url.rstrip("/"), key, bucket


def is_configured() -> bool:
    config = current_app.config
    return bool(
        config.get("SUPABASE_URL")
        and config.get("SUPABASE_SERVICE_ROLE_KEY")
        and config.get("SUPABASE_STORAGE_BUCKET")
    )


def _request(method: str, path: str, *, data: bytes | None = None, headers: dict | None = None):
    base_url, key, _bucket = _config()
    request = urllib.request.Request(
        f"{base_url}/storage/v1{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {key}",
            "apikey": key,
            **(headers or {}),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15, context=_SSL_CONTEXT) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SupabaseStorageError(f"Supabase Storage returned {exc.code}: {body[:300]}") from exc
    except urllib.error.URLError as exc:
        raise SupabaseStorageError(f"Could not reach Supabase Storage: {exc.reason}") from exc


def ensure_public_bucket() -> None:
    """Create the configured bucket as public if it does not already exist."""
    _base_url, _key, bucket = _config()
    try:
        _request(
            "POST",
            "/bucket",
            data=json.dumps({"id": bucket, "name": bucket, "public": True}).encode(),
            headers={"Content-Type": "application/json"},
        )
    except SupabaseStorageError as exc:
        # "already exists" is the expected steady state -- everything else is real.
        if "already exists" not in str(exc) and "duplicate" not in str(exc).lower():
            raise


def upload(storage_key: str, data: bytes, content_type: str) -> str:
    """Upload one object, overwriting any existing file at that key. Returns its public URL."""
    _base_url, _key, bucket = _config()
    try:
        _request(
            "POST",
            f"/object/{bucket}/{storage_key}",
            data=data,
            headers={"Content-Type": content_type, "x-upsert": "true"},
        )
    except SupabaseStorageError as exc:
        raise ValidationError(
            "Some fields need attention.",
            fields={"file": "The image could not be uploaded. Please try again."},
        ) from exc
    return public_url(storage_key)


def delete(storage_key: str) -> None:
    """Remove one object. A missing object is not an error."""
    if not storage_key:
        return
    _base_url, _key, bucket = _config()
    try:
        _request("DELETE", f"/object/{bucket}/{storage_key}")
    except SupabaseStorageError:
        # Deleting an already-gone file should not block the caller (an admin
        # removing a gallery row whose file was already cleaned up manually).
        pass


def public_url(storage_key: str) -> str:
    base_url, _key, bucket = _config()
    return f"{base_url}/storage/v1/object/public/{bucket}/{storage_key}"
