"""Admin event CRUD."""

from __future__ import annotations

from flask import Blueprint, jsonify

from ..security import admin_required
from ..services import event_service
from ..validation import Payload, json_body, pagination, query_bool, query_str

bp = Blueprint("admin_events", __name__)

ALLOWED = event_service.EDITABLE_FIELDS


def _validate(raw: dict, *, is_new: bool) -> dict:
    body = Payload(raw, allowed=ALLOWED)
    body.string("title", required=is_new, max_length=200)
    body.slug("slug", nullable=True)
    body.string("summary", max_length=300, nullable=True, min_length=0)
    body.text("description", max_length=60000, nullable=True)
    body.datetime_("starts_at", required=is_new, nullable=False)
    body.datetime_("ends_at")
    body.string("location", max_length=200, nullable=True, min_length=0)
    body.url("cover_image_url")
    body.boolean("is_published", default=False if is_new else None)
    data = body.done()
    if not is_new:
        data = {key: value for key, value in data.items() if key in raw}
    return data


@bp.get("/admin/events")
@admin_required()
def list_events():
    page, per_page = pagination()
    return jsonify(
        event_service.list_admin(
            page, per_page, published=query_bool("published"), search=query_str("q")
        )
    ), 200


@bp.post("/admin/events")
@admin_required()
def create_event():
    data = _validate(json_body(), is_new=True)
    return jsonify(event_service.create(data).to_admin_dict()), 201


@bp.get("/admin/events/<int:event_id>")
@admin_required()
def get_event(event_id: int):
    return jsonify(event_service.get_admin(event_id).to_admin_dict()), 200


@bp.put("/admin/events/<int:event_id>")
@admin_required()
def update_event(event_id: int):
    event = event_service.get_admin(event_id)
    data = _validate(json_body(), is_new=False)
    return jsonify(event_service.update(event, data).to_admin_dict()), 200


@bp.patch("/admin/events/<int:event_id>/publish")
@admin_required()
def publish_event(event_id: int):
    event = event_service.get_admin(event_id)
    body = Payload(json_body(), allowed={"is_published"})
    body.boolean("is_published", required=True)
    data = body.done()
    return jsonify(event_service.set_published(event, data["is_published"]).to_admin_dict()), 200


@bp.delete("/admin/events/<int:event_id>")
@admin_required()
def delete_event(event_id: int):
    event_service.delete(event_service.get_admin(event_id))
    return "", 204
