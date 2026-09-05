"""Infrastructure tables: the JWT blocklist and the rate-limit ledger.

Neither is part of the site's content model, but both have to live in
PostgreSQL rather than process memory: gunicorn runs several workers, and a
per-process counter would multiply every allowance by the worker count while a
per-process blocklist would let a revoked token keep working on another worker.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..extensions import db
from . import utcnow


class TokenBlocklist(db.Model):
    """Revoked JWTs, by jti. Logout writes here; every request checks here."""

    __tablename__ = "token_blocklist"
    __table_args__ = (
        Index("ix_token_blocklist_jti", "jti", unique=True),
        Index("ix_token_blocklist_expires", "expires_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    jti: Mapped[str] = mapped_column(String(64), nullable=False)
    token_type: Mapped[str] = mapped_column(String(16), nullable=False)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("admin_users.id", ondelete="CASCADE"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RateLimitHit(db.Model):
    """One row per counted attempt. Old rows are swept as new ones arrive."""

    __tablename__ = "rate_limit_hits"
    __table_args__ = (Index("ix_rate_limit_hits_lookup", "bucket", "identifier", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    bucket: Mapped[str] = mapped_column(String(60), nullable=False)
    identifier: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )
