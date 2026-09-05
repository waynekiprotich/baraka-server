"""Public gallery endpoints."""

from __future__ import annotations

from flask import Blueprint, jsonify

from ..services import gallery_service
from ..validation import pagination, query_str

bp = Blueprint("gallery", __name__)


@bp.get("/gallery/categories")
def gallery_categories():
    return jsonify({"items": gallery_service.list_categories()}), 200


@bp.get("/gallery")
def list_gallery():
    page, per_page = pagination()
    return jsonify(
        gallery_service.list_public_images(
            page, per_page, category_slug=query_str("category", max_length=120)
        )
    ), 200
