"""News articles."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from ..extensions import db
from ..validation import iso
from . import utcnow


class NewsArticle(db.Model):
    __tablename__ = "news_articles"
    __table_args__ = (
        Index("ix_news_articles_slug", "slug", unique=True),
        Index("ix_news_articles_published", "is_published", "published_at"),
        Index("ix_news_articles_category", "category"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(200), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    excerpt: Mapped[str | None] = mapped_column(String(300), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    category: Mapped[str | None] = mapped_column(String(80), nullable=True)
    cover_image_url: Mapped[str | None] = mapped_column(String(600), nullable=True)
    cover_image_alt: Mapped[str | None] = mapped_column(String(300), nullable=True)
    author: Mapped[str | None] = mapped_column(String(120), nullable=True)
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False,
                                               server_default=text("false"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow,
        server_default=func.now()
    )

    def to_public_dict(self, *, include_body: bool = False) -> dict:
        data = {
            "id": self.id,
            "slug": self.slug,
            "title": self.title,
            "excerpt": self.excerpt,
            "category": self.category,
            "cover_image_url": self.cover_image_url,
            "cover_image_alt": self.cover_image_alt,
            "author": self.author,
            "published_at": iso(self.published_at),
        }
        if include_body:
            data["body"] = self.body
        return data

    def to_admin_dict(self) -> dict:
        data = self.to_public_dict(include_body=True)
        data.update(
            {
                "is_published": self.is_published,
                "created_at": iso(self.created_at),
                "updated_at": iso(self.updated_at),
            }
        )
        return data
