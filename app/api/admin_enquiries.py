"""Admin enquiry inbox."""

from __future__ import annotations

from flask import Blueprint, jsonify

from ..models import ENQUIRY_STATUSES
from ..services import enquiry_service
from ..security import admin_required
from ..validation import Payload, json_body, pagination, query_str

bp = Blueprint("admin_enquiries", __name__)


@bp.get("/admin/enquiries")
@admin_required()
def list_enquiries():
    page, per_page = pagination()
    return jsonify(
        enquiry_service.list_admin(
            page, per_page, status=query_str("status", max_length=20), search=query_str("q")
        )
    ), 200


@bp.get("/admin/enquiries/<int:enquiry_id>")
@admin_required()
def get_enquiry(enquiry_id: int):
    return jsonify(enquiry_service.get(enquiry_id).to_dict()), 200


@bp.patch("/admin/enquiries/<int:enquiry_id>")
@admin_required()
def update_enquiry(enquiry_id: int):
    enquiry = enquiry_service.get(enquiry_id)
    body = Payload(json_body(), allowed={"status"})
    body.enum("status", ENQUIRY_STATUSES, required=True)
    data = body.done()
    return jsonify(enquiry_service.set_status(enquiry, data["status"]).to_dict()), 200


@bp.delete("/admin/enquiries/<int:enquiry_id>")
@admin_required()
def delete_enquiry(enquiry_id: int):
    enquiry_service.delete(enquiry_service.get(enquiry_id))
    return "", 204
