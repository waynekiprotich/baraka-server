"""Admin settings: read every row, write a {key: value} map."""

from __future__ import annotations

from flask import Blueprint, jsonify

from ..security import admin_required
from ..services import settings_service
from ..validation import Payload, json_body

bp = Blueprint("admin_settings", __name__)


@bp.get("/admin/settings")
@admin_required()
def get_settings():
    return jsonify({"items": settings_service.admin_list()}), 200


@bp.put("/admin/settings")
@admin_required()
def put_settings():
    body = Payload(json_body(), allowed={"values"})
    body.object_of_strings("values", required=True)
    data = body.done()
    return jsonify({"items": settings_service.update_many(data["values"])}), 200
