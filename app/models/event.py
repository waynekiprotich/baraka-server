"""School events."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from ..extensions import db
from ..validation import iso
from . import utcnow


class Event(db.Model):
    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint("ends_at IS NULL OR ends_at >= starts_at", name="ck_events_end_after_start"),
        Index("ix_events_slug", "slug", unique=True),
        Index("ix_events_published_start", "is_published", "starts_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(200), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str | None] = mapped_column(String(300), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    cover_image_url: Mapped[str | None] = mapped_column(String(600), nullable=True)
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False,
                                               server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow,
        server_default=func.now()
    )

    def to_public_dict(self, *, include_description: bool = False) -> dict:
        data = {
            "id": self.id,
            "slug": self.slug,
            "title": self.title,
            "summary": self.summary,
            "starts_at": iso(self.starts_at),
            "ends_at": iso(self.ends_at),
            "location": self.location,
            "cover_image_url": self.cover_image_url,
        }
        if include_description:
            data["description"] = self.description
        return data

    def to_admin_dict(self) -> dict:
        data = self.to_public_dict(include_description=True)
        data.update(
            {
                "is_published": self.is_published,
                "created_at": iso(self.created_at),
                "updated_at": iso(self.updated_at),
            }
        )
        return data
