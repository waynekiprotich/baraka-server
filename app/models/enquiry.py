"""Enquiries submitted from the contact and admissions forms."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..extensions import db
from ..validation import iso
from . import utcnow

ENQUIRY_SOURCES = ("contact", "admissions")
ENQUIRY_STATUSES = ("new", "read", "archived")


class Enquiry(db.Model):
    __tablename__ = "enquiries"
    __table_args__ = (
        CheckConstraint("source IN ('contact', 'admissions')", name="ck_enquiries_source"),
        CheckConstraint("status IN ('new', 'read', 'archived')", name="ck_enquiries_status"),
        Index("ix_enquiries_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    subject: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Stored and returned as plain text. Never rendered as HTML anywhere.
    message: Mapped[str] = mapped_column(Text, nullable=False)
    learner_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    grade_applying: Mapped[str | None] = mapped_column(String(40), nullable=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="contact",
                                        server_default="contact")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="new",
                                        server_default="new")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )
    # A salted hash, never the address itself -- enough to spot abuse, not
    # enough to track a visitor.
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "phone": self.phone,
            "subject": self.subject,
            "message": self.message,
            "learner_name": self.learner_name,
            "grade_applying": self.grade_applying,
            "source": self.source,
            "status": self.status,
            "created_at": iso(self.created_at),
        }
