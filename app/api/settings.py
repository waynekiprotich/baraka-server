"""Public settings endpoint: a flat {key: value} map the whole site reads."""

from __future__ import annotations

from flask import Blueprint, jsonify

from ..services import settings_service

bp = Blueprint("settings", __name__)


@bp.get("/settings")
def public_settings():
    return jsonify(settings_service.public_map()), 200
