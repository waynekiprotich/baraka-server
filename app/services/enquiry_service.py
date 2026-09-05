"""Enquiries: the one thing an anonymous visitor may write to the database."""

from __future__ import annotations

from sqlalchemy import func, select

from ..errors import NotFoundError, ValidationError
from ..extensions import db
from ..models import ENQUIRY_STATUSES, Enquiry
from ..security import client_ip, hash_ip
from . import paginate, rate_limit

ENQUIRY_BUCKET = "enquiry_create"

# A field no real visitor fills in. A bot that fills every input gives itself
# away, and we accept the request quietly rather than teaching it otherwise.
HONEYPOT_FIELD = "website"


def create(data: dict, honeypot_value: str | None) -> Enquiry | None:
    """Store an enquiry. Returns None when the honeypot was tripped."""
    rate_limit.enforce(ENQUIRY_BUCKET, client_ip())

    if honeypot_value:
        return None

    enquiry = Enquiry(
        name=data["name"],
        email=data["email"],
        phone=data.get("phone") or None,
        subject=data.get("subject") or None,
        message=data["message"],
        learner_name=data.get("learner_name") or None,
        grade_applying=data.get("grade_applying") or None,
        source=data.get("source") or "contact",
        status="new",
        ip_hash=hash_ip(client_ip()),
    )
    db.session.add(enquiry)
    db.session.commit()
    return enquiry


def list_admin(page: int, per_page: int, status: str | None = None, search: str | None = None):
    stmt = select(Enquiry)
    if status:
        if status not in ENQUIRY_STATUSES:
            raise ValidationError(
                "Some fields need attention.",
                fields={"status": "Must be one of: " + ", ".join(ENQUIRY_STATUSES) + "."},
            )
        stmt = stmt.where(Enquiry.status == status)
    if search:
        pattern = f"%{search.lower()}%"
        stmt = stmt.where(
            func.lower(Enquiry.name).like(pattern) | func.lower(Enquiry.email).like(pattern)
        )
    stmt = stmt.order_by(Enquiry.created_at.desc(), Enquiry.id.desc())
    rows, envelope = paginate(stmt, page, per_page)
    envelope["items"] = [row.to_dict() for row in rows]
    envelope["counts"] = status_counts()
    return envelope


def status_counts() -> dict[str, int]:
    rows = db.session.execute(
        select(Enquiry.status, func.count(Enquiry.id)).group_by(Enquiry.status)
    ).all()
    counts = {status: 0 for status in ENQUIRY_STATUSES}
    for status, count in rows:
        counts[status] = count
    counts["total"] = sum(counts[status] for status in ENQUIRY_STATUSES)
    return counts


def get(enquiry_id: int) -> Enquiry:
    enquiry = db.session.get(Enquiry, enquiry_id)
    if enquiry is None:
        raise NotFoundError("That enquiry does not exist.")
    return enquiry


def set_status(enquiry: Enquiry, status: str) -> Enquiry:
    enquiry.status = status
    db.session.commit()
    return enquiry


def delete(enquiry: Enquiry) -> None:
    db.session.delete(enquiry)
    db.session.commit()
