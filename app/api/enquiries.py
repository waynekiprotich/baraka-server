"""Public enquiry submission -- the contact and admissions forms."""

from __future__ import annotations

from flask import Blueprint, jsonify

from ..models import ENQUIRY_SOURCES
from ..services import enquiry_service
from ..validation import Payload, json_body

bp = Blueprint("enquiries", __name__)

ALLOWED = {
    "name",
    "email",
    "phone",
    "subject",
    "message",
    "learner_name",
    "grade_applying",
    "source",
    enquiry_service.HONEYPOT_FIELD,
}


@bp.post("/enquiries")
def create_enquiry():
    raw = json_body()
    body = Payload(raw, allowed=ALLOWED)
    body.string("name", required=True, min_length=2, max_length=120)
    body.email("email", required=True)
    body.phone("phone")
    body.string("subject", max_length=200, nullable=True, min_length=0)
    body.text("message", required=True, max_length=5000)
    body.string("learner_name", max_length=120, nullable=True, min_length=0)
    body.string("grade_applying", max_length=40, nullable=True, min_length=0)
    body.enum("source", ENQUIRY_SOURCES, default="contact")
    # The honeypot is accepted but never stored.
    body.string(
        enquiry_service.HONEYPOT_FIELD, max_length=200, nullable=True, min_length=0
    )
    data = body.done()

    honeypot = data.get(enquiry_service.HONEYPOT_FIELD)
    enquiry = enquiry_service.create(data, honeypot)

    # A tripped honeypot gets the same 201 a person gets: a bot learns nothing.
    return jsonify(
        {
            "ok": True,
            "id": enquiry.id if enquiry is not None else None,
            "message": "Thank you — your message has been received.",
        }
    ), 201
