"""Image upload, and the static route the stored files are served from."""

from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, jsonify, request, send_from_directory

from ..errors import NotFoundError, UnsupportedMediaTypeError
from ..security import admin_required
from ..services import image_service

bp = Blueprint("admin_uploads", __name__)

# Registered on the app, not under /api/v1: these are the URLs stored in rows.
files_bp = Blueprint("uploaded_files", __name__, url_prefix="/uploads")

SERVABLE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
CONTENT_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


@bp.post("/admin/uploads")
@admin_required()
def upload_image():
    result = image_service.process_upload(request.files.get("file"))
    return jsonify(result), 201


@files_bp.get("/<path:filename>")
def serve_upload(filename: str):
    # The filename we generated is a uuid4 hex plus a known suffix; anything
    # else is refused before it reaches the filesystem.
    name = Path(filename).name
    if name != filename or not name:
        raise NotFoundError("That file does not exist.")
    suffix = Path(name).suffix.lower()
    if suffix not in SERVABLE_SUFFIXES:
        raise UnsupportedMediaTypeError("That file type is not served from here.")
    directory = Path(current_app.config["UPLOAD_DIR"])
    if not (directory / name).is_file():
        raise NotFoundError("That file does not exist.")
    response = send_from_directory(directory, name, mimetype=CONTENT_TYPES[suffix])
    # The name is content-addressed by uuid, so it can be cached forever.
    response.headers["Cache-Control"] = current_app.config["IMMUTABLE_CACHE_CONTROL"]
    return response
