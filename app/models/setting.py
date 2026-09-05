"""Site settings: the school's own editable copy, keyed by name."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..extensions import db
from ..validation import iso
from . import utcnow

SETTING_VALUE_TYPES = ("string", "text", "number", "url", "bool", "json")


class SiteSetting(db.Model):
    __tablename__ = "site_settings"
    __table_args__ = (
        CheckConstraint(
            "value_type IN ('string', 'text', 'number', 'url', 'bool', 'json')",
            name="ck_site_settings_value_type",
        ),
        Index("ix_site_settings_group", "group"),
    )

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    value_type: Mapped[str] = mapped_column(String(16), nullable=False, default="string",
                                            server_default="string")
    group: Mapped[str] = mapped_column("group", String(40), nullable=False, default="general",
                                       server_default="general")
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow,
        server_default=func.now()
    )

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "value": self.value,
            "value_type": self.value_type,
            "group": self.group,
            "label": self.label,
            "updated_at": iso(self.updated_at),
        }
