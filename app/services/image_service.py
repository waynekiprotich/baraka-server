"""Upload handling.

An uploaded file is never trusted. The extension and the client's declared
content-type are ignored entirely; the bytes are decoded with Pillow and only a
JPEG, PNG or WebP that actually decodes is accepted. The pixels are then copied
into a fresh image -- which is what strips EXIF, colour profiles and any
appended payload -- re-encoded, capped at 2000px on the long edge, and written
under a `uuid4().hex` name. The client's filename never touches the disk.
"""

from __future__ import annotations

import io
import uuid
from pathlib import Path

from flask import current_app
from PIL import Image, ImageOps, UnidentifiedImageError

from ..errors import PayloadTooLargeError, UnsupportedMediaTypeError, ValidationError
from . import imagekit_storage, supabase_storage

CONTENT_TYPES = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}

# Pillow format -> (file extension, save format, save kwargs)
FORMAT_SETTINGS = {
    "JPEG": (".jpg", "JPEG", {"quality": 82, "optimize": True, "progressive": True}),
    "PNG": (".png", "PNG", {"optimize": True}),
    "WEBP": (".webp", "WEBP", {"quality": 82, "method": 4}),
}

READ_CHUNK = 64 * 1024


def upload_dir() -> Path:
    directory = Path(current_app.config["UPLOAD_DIR"])
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def read_within_limit(stream, limit: int) -> bytes:
    """Read at most `limit` bytes; one byte more and the upload is rejected."""
    buffer = io.BytesIO()
    total = 0
    while True:
        chunk = stream.read(READ_CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise PayloadTooLargeError(
                f"Images must be {limit // (1024 * 1024)} MB or smaller."
            )
        buffer.write(chunk)
    return buffer.getvalue()


def process_upload(file_storage) -> dict:
    """Validate, sanitise and store one uploaded image."""
    if file_storage is None or not getattr(file_storage, "filename", ""):
        raise ValidationError(
            "Some fields need attention.", fields={"file": "Choose an image to upload."}
        )

    config = current_app.config
    raw = read_within_limit(file_storage.stream, config["MAX_UPLOAD_BYTES"])
    if not raw:
        raise ValidationError(
            "Some fields need attention.", fields={"file": "That file is empty."}
        )

    # Decode twice: verify() proves the container parses, then a fresh open is
    # required because verify() leaves the image unusable.
    try:
        with Image.open(io.BytesIO(raw)) as probe:
            probe.verify()
        source = Image.open(io.BytesIO(raw))
        source.load()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise UnsupportedMediaTypeError(
            "That file is not a readable JPEG, PNG or WebP image."
        ) from exc

    with source:
        image_format = (source.format or "").upper()
        if image_format not in config["UPLOAD_ALLOWED_FORMATS"]:
            raise UnsupportedMediaTypeError(
                "Images must be JPEG, PNG or WebP."
            )
        extension, save_format, save_kwargs = FORMAT_SETTINGS[image_format]

        oriented = ImageOps.exif_transpose(source) or source
        clean = _strip_metadata(oriented, save_format)

    name = uuid.uuid4().hex
    full = _fit(clean, config["UPLOAD_MAX_EDGE"])
    full_name = f"{name}{extension}"
    content_type = CONTENT_TYPES[image_format]

    # ImageKit takes priority when configured, then Supabase Storage, then local
    # disk -- the same order tried at request time, not baked in anywhere else.
    if imagekit_storage.is_configured():
        record = imagekit_storage.upload(full_name, _encode(full, save_format, save_kwargs), content_type)
        url = record["url"]
        # ImageKit resizes on the fly from one stored file -- no second upload,
        # no separate thumbnail file to keep in sync or clean up later.
        thumb_url = imagekit_storage.thumbnail_url(url, config["UPLOAD_THUMB_EDGE"])
        # The fileId, not the filename, is what ImageKit's delete API takes.
        storage_key = record["fileId"]
        width, height = full.size
        full.close()
        clean.close()
        return {
            "url": url,
            "thumb_url": thumb_url,
            "width": width,
            "height": height,
            "storage_key": storage_key,
        }

    thumb = _fit(clean, config["UPLOAD_THUMB_EDGE"])
    thumb_name = f"{name}_thumb{extension}"

    if supabase_storage.is_configured():
        url = supabase_storage.upload(full_name, _encode(full, save_format, save_kwargs), content_type)
        thumb_url = supabase_storage.upload(
            thumb_name, _encode(thumb, save_format, save_kwargs), content_type
        )
    else:
        directory = upload_dir()
        _save(full, directory / full_name, save_format, save_kwargs)
        _save(thumb, directory / thumb_name, save_format, save_kwargs)
        url = f"/uploads/{full_name}"
        thumb_url = f"/uploads/{thumb_name}"

    width, height = full.size
    for image in (full, thumb, clean):
        image.close()

    return {
        "url": url,
        "thumb_url": thumb_url,
        "width": width,
        "height": height,
        "storage_key": full_name,
    }


def delete_stored(storage_key: str | None, url: str | None = None) -> None:
    """Remove a stored image and its thumbnail. Missing files are not an error.

    Routed by the URL's own host, not by whichever backend the environment
    currently has configured: a row created under one backend must still
    delete correctly after the active backend changes (e.g. ImageKit keys
    added after a run of images were already stored in Supabase).
    """
    if not storage_key:
        return

    if url and ".imagekit.io/" in url:
        # storage_key holds the ImageKit fileId for rows stored this way.
        imagekit_storage.delete(storage_key)
        return

    if url and "supabase.co/storage/v1/object/public/" in url:
        name = Path(storage_key).name
        if name and name == storage_key:
            stem, _, suffix = name.rpartition(".")
            supabase_storage.delete(name)
            if stem:
                supabase_storage.delete(f"{stem}_thumb.{suffix}")
        return

    # Guard against a stored key that tries to escape the upload directory.
    name = Path(storage_key).name
    if not name or name != storage_key:
        return
    stem, _, suffix = name.rpartition(".")
    thumb_name = f"{stem}_thumb.{suffix}" if stem else ""

    directory = upload_dir()
    for candidate in (name, thumb_name):
        if not candidate:
            continue
        path = directory / candidate
        if path.is_file():
            path.unlink()


def _strip_metadata(image: Image.Image, save_format: str) -> Image.Image:
    """Copy the pixels into a brand-new image, leaving every metadata block behind."""
    mode = image.mode
    if save_format == "JPEG":
        if mode not in ("RGB", "L"):
            image = image.convert("RGB")
            mode = "RGB"
    elif mode not in ("RGB", "RGBA", "L", "LA"):
        image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
        mode = image.mode
    # frombytes() builds an image from raw pixels only -- no info dict, no EXIF,
    # no ICC profile, no trailing bytes from the original file.
    return Image.frombytes(mode, image.size, image.tobytes())


def _fit(image: Image.Image, max_edge: int) -> Image.Image:
    copy = image.copy()
    if max(copy.size) > max_edge:
        copy.thumbnail((max_edge, max_edge), Image.LANCZOS)
    return copy


def _save(image: Image.Image, path: Path, save_format: str, save_kwargs: dict) -> None:
    to_write = image
    if save_format == "WEBP" and image.mode not in ("RGB", "RGBA"):
        to_write = image.convert("RGBA")
    to_write.save(path, format=save_format, **save_kwargs)


def _encode(image: Image.Image, save_format: str, save_kwargs: dict) -> bytes:
    to_write = image
    if save_format == "WEBP" and image.mode not in ("RGB", "RGBA"):
        to_write = image.convert("RGBA")
    buffer = io.BytesIO()
    to_write.save(buffer, format=save_format, **save_kwargs)
    return buffer.getvalue()
