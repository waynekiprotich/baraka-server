"""Authentication endpoints."""

from __future__ import annotations

from flask import Blueprint, jsonify

from ..security import admin_required, current_admin, load_admin_from_token
from ..services import auth_service
from ..validation import Payload, json_body

bp = Blueprint("auth", __name__)


@bp.post("/auth/login")
def login():
    body = Payload(json_body(), allowed={"email", "password"})
    body.email("email", required=True)
    body.string("password", required=True, min_length=1, max_length=256, strip=False)
    data = body.done()

    user = auth_service.authenticate(data["email"], data["password"])
    return jsonify(auth_service.issue_tokens(user)), 200


@bp.post("/auth/refresh")
@admin_required(refresh=True)
def refresh():
    user = current_admin()
    return jsonify(auth_service.issue_access_token(user)), 200


@bp.post("/auth/logout")
@admin_required()
def logout():
    user = current_admin()
    auth_service.revoke_current_token(user.id)
    return "", 204


@bp.post("/auth/logout-refresh")
@admin_required(refresh=True)
def logout_refresh():
    """Revoke the refresh token too, so signing out ends the whole session."""
    user = load_admin_from_token()
    auth_service.revoke_current_token(user.id)
    return "", 204


@bp.get("/auth/me")
@admin_required()
def me():
    return jsonify({"user": current_admin().to_dict()}), 200


@bp.post("/auth/change-password")
@admin_required()
def change_password():
    body = Payload(json_body(), allowed={"current_password", "new_password"})
    body.string("current_password", required=True, min_length=1, max_length=256, strip=False)
    body.string("new_password", required=True, min_length=1, max_length=256, strip=False)
    data = body.done()

    auth_service.change_password(
        current_admin(), data["current_password"], data["new_password"]
    )
    return jsonify({"ok": True}), 200
