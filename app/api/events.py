"""Public event endpoints."""

from __future__ import annotations

from flask import Blueprint, jsonify

from ..services import event_service
from ..validation import pagination, query_bool

bp = Blueprint("events", __name__)


@bp.get("/events")
def list_events():
    page, per_page = pagination()
    return jsonify(
        event_service.list_public(page, per_page, upcoming=query_bool("upcoming"))
    ), 200


@bp.get("/events/<slug>")
def event_detail(slug: str):
    event = event_service.get_public_by_slug(slug)
    return jsonify(event.to_public_dict(include_description=True)), 200
