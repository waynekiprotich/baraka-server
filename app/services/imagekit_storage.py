"""ImageKit client for uploaded images.

Talks to the ImageKit Upload/Media APIs directly over `urllib`, matching the
pattern already used for Supabase Storage -- a handful of small HTTP calls do
not justify a new dependency (no `imagekitio` SDK, no `requests`).

Design note on the upload flow: ImageKit's client-side ("browser-direct")
upload pattern authenticates the *browser* with a short-lived signature
(token + expire + HMAC-SHA1(privateKey, token+expire)), so the browser never
holds the private key. This project deliberately does not use that pattern --
the file is still posted to Flask first, exactly as before, so it keeps
passing through the existing Pillow pipeline (decode-validate, EXIF/GPS strip,
re-encode, resize) before anything is stored anywhere. That pipeline is a real
security and privacy property -- this is a school site with photos of
children, and stripping embedded GPS data is not optional -- and a
browser-direct upload would bypass it entirely.

"Flask generates secure upload authentication parameters" is satisfied here by
Flask being the only thing that ever constructs the authenticated request to
ImageKit: every call authenticates with HTTP Basic Auth, username the private
key, password blank, built fresh per request and never returned to a caller.
`auth_header()` is the one function that touches the private key.
"""

from __future__ import annotations

import base64
import io
import json
import ssl
import urllib.error
import urllib.request
import uuid

import certifi
from flask import current_app

from ..errors import ValidationError

UPLOAD_URL = "https://upload.imagekit.io/api/v1/files/upload"
API_BASE = "https://api.imagekit.io/v1"

# Same pinned CA bundle used for Supabase -- see supabase_storage.py for why.
_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())


class ImageKitError(RuntimeError):
    """The ImageKit API rejected a request or was unreachable."""


def _private_key() -> str:
    key = current_app.config.get("IMAGEKIT_PRIVATE_KEY")
    if not key:
        raise ImageKitError("IMAGEKIT_PRIVATE_KEY is not configured.")
    return key


def is_configured() -> bool:
    config = current_app.config
    return bool(
        config.get("IMAGEKIT_PUBLIC_KEY")
        and config.get("IMAGEKIT_PRIVATE_KEY")
        and config.get("IMAGEKIT_URL_ENDPOINT")
    )


def auth_header() -> dict:
    """The Basic Auth header ImageKit expects: the private key as username, no password."""
    token = base64.b64encode(f"{_private_key()}:".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def _multipart(fields: dict, file_field: str, filename: str, content_type: str, data: bytes):
    boundary = uuid.uuid4().hex
    buffer = io.BytesIO()

    def write_field(name: str, value: str) -> None:
        buffer.write(f"--{boundary}\r\n".encode())
        buffer.write(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        buffer.write(value.encode())
        buffer.write(b"\r\n")

    for name, value in fields.items():
        write_field(name, value)

    buffer.write(f"--{boundary}\r\n".encode())
    buffer.write(
        f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'.encode()
    )
    buffer.write(f"Content-Type: {content_type}\r\n\r\n".encode())
    buffer.write(data)
    buffer.write(b"\r\n")

    buffer.write(f"--{boundary}--\r\n".encode())
    return f"multipart/form-data; boundary={boundary}", buffer.getvalue()


def _request(method: str, url: str, *, data: bytes | None = None, headers: dict):
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=20, context=_SSL_CONTEXT) as response:
            body = response.read()
            return response.status, json.loads(body) if body else None
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise ImageKitError(f"ImageKit returned {exc.code}: {body[:300]}") from exc
    except urllib.error.URLError as exc:
        raise ImageKitError(f"Could not reach ImageKit: {exc.reason}") from exc


def upload(filename: str, data: bytes, content_type: str, *, folder: str = "/gallery") -> dict:
    """Upload one file. Returns ImageKit's record: url, thumbnailUrl, fileId, filePath, ..."""
    content_type_header, body = _multipart(
        {"fileName": filename, "folder": folder, "useUniqueFileName": "true"},
        "file",
        filename,
        content_type,
        data,
    )
    try:
        _status, payload = _request(
            "POST",
            UPLOAD_URL,
            data=body,
            headers={**auth_header(), "Content-Type": content_type_header},
        )
    except ImageKitError as exc:
        raise ValidationError(
            "Some fields need attention.",
            fields={"file": "The image could not be uploaded. Please try again."},
        ) from exc
    return payload


def delete(file_id: str) -> None:
    """Remove one file by its ImageKit fileId. A missing file is not an error."""
    if not file_id:
        return
    try:
        _request("DELETE", f"{API_BASE}/files/{file_id}", headers=auth_header())
    except ImageKitError:
        # Deleting an already-gone file should not block the caller (an admin
        # removing a gallery row whose file was already cleaned up manually).
        pass


def thumbnail_url(url: str, edge: int) -> str:
    """An on-the-fly resized variant of an ImageKit URL -- no second file is stored."""
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}tr=w-{edge},h-{edge},c-at_max"
