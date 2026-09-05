"""The one account type in the system: a school administrator."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, String, func, text
from sqlalchemy.orm import Mapped, mapped_column
from werkzeug.security import check_password_hash, generate_password_hash

from ..extensions import db
from ..validation import iso
from . import utcnow


class AdminUser(db.Model):
    __tablename__ = "admin_users"
    __table_args__ = (
        # Emails are stored lowercased so uniqueness is case-insensitive
        # without depending on the citext extension being installed.
        CheckConstraint("email = lower(email)", name="ck_admin_users_email_lowercase"),
        Index("ix_admin_users_email", "email", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True,
                                            server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def set_password(self, raw_password: str) -> None:
        self.password_hash = generate_password_hash(raw_password, method="scrypt")

    def check_password(self, raw_password: str) -> bool:
        return check_password_hash(self.password_hash, raw_password)

    def to_dict(self) -> dict:
        """The user shape returned by /auth/login and /auth/me. No hash, ever."""
        return {
            "id": self.id,
            "email": self.email,
            "name": self.name,
            "is_active": self.is_active,
            "created_at": iso(self.created_at),
            "last_login_at": iso(self.last_login_at),
        }
