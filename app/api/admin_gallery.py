"""Admin gallery: categories, images, and the ordering endpoint."""

from __future__ import annotations

from flask import Blueprint, jsonify

from ..security import admin_required
from ..services import gallery_service, image_service
from ..validation import Payload, json_body, pagination, query_int

bp = Blueprint("admin_gallery", __name__)


# --- categories -----------------------------------------------------------


def _validate_category(raw: dict, *, is_new: bool) -> dict:
    body = Payload(raw, allowed=gallery_service.CATEGORY_FIELDS)
    body.string("name", required=is_new, max_length=120)
    body.slug("slug", nullable=True)
    body.text("description", max_length=2000, nullable=True)
    body.integer("position", minimum=0, maximum=100000, default=0 if is_new else None)
    data = body.done()
    if not is_new:
        data = {key: value for key, value in data.items() if key in raw}
    return data


@bp.get("/admin/gallery/categories")
@admin_required()
def list_categories():
    return jsonify({"items": gallery_service.list_categories()}), 200


@bp.post("/admin/gallery/categories")
@admin_required()
def create_category():
    data = _validate_category(json_body(), is_new=True)
    category = gallery_service.create_category(data)
    return jsonify(category.to_dict(image_count=0)), 201


@bp.put("/admin/gallery/categories/<int:category_id>")
@admin_required()
def update_category(category_id: int):
    category = gallery_service.get_category(category_id)
    data = _validate_category(json_body(), is_new=False)
    updated = gallery_service.update_category(category, data)
    return jsonify(updated.to_dict(image_count=len(updated.images))), 200


@bp.delete("/admin/gallery/categories/<int:category_id>")
@admin_required()
def delete_category(category_id: int):
    gallery_service.delete_category(gallery_service.get_category(category_id))
    return "", 204


# --- images ---------------------------------------------------------------


def _validate_image(raw: dict, *, is_new: bool) -> dict:
    body = Payload(raw, allowed=gallery_service.IMAGE_FIELDS)
    body.integer("category_id", nullable=True, minimum=1)
    body.string("title", max_length=200, nullable=True, min_length=0)
    body.string("alt_text", required=is_new, max_length=300)
    body.url("url", required=is_new, nullable=False)
    body.url("thumb_url")
    body.string("storage_key", max_length=200, nullable=True, min_length=0)
    body.integer("width", nullable=True, minimum=1, maximum=100000)
    body.integer("height", nullable=True, minimum=1, maximum=100000)
    body.integer("position", minimum=0, maximum=100000)
    body.boolean("is_featured", default=False if is_new else None)
    data = body.done()
    if not is_new:
        data = {key: value for key, value in data.items() if key in raw}
    return data


@bp.get("/admin/gallery/images")
@admin_required()
def list_images():
    page, per_page = pagination()
    category_id = query_int("category_id", 0, minimum=0, maximum=10**9) or None
    return jsonify(gallery_service.list_admin_images(page, per_page, category_id)), 200


@bp.post("/admin/gallery/images")
@admin_required()
def create_image():
    data = _validate_image(json_body(), is_new=True)
    return jsonify(gallery_service.create_image(data).to_admin_dict()), 201


@bp.get("/admin/gallery/images/<int:image_id>")
@admin_required()
def get_image(image_id: int):
    return jsonify(gallery_service.get_image(image_id).to_admin_dict()), 200


@bp.put("/admin/gallery/images/<int:image_id>")
@admin_required()
def update_image(image_id: int):
    image = gallery_service.get_image(image_id)
    data = _validate_image(json_body(), is_new=False)
    return jsonify(gallery_service.update_image(image, data).to_admin_dict()), 200


@bp.delete("/admin/gallery/images/<int:image_id>")
@admin_required()
def delete_image(image_id: int):
    image = gallery_service.get_image(image_id)
    storage_key = image.storage_key
    url = image.url
    gallery_service.delete_image(image)
    # The row is gone, so the file behind it should go too.
    image_service.delete_stored(storage_key, url)
    return "", 204


@bp.post("/admin/gallery/images/reorder")
@admin_required()
def reorder_images():
    body = Payload(json_body(), allowed={"ids"})
    body.int_list("ids", required=True)
    data = body.done()
    return jsonify({"items": gallery_service.reorder_images(data["ids"])}), 200
