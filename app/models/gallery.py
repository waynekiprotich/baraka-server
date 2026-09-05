"""Photo gallery: categories and the images inside them."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db
from ..validation import iso
from . import utcnow


class GalleryCategory(db.Model):
    __tablename__ = "gallery_categories"
    __table_args__ = (Index("ix_gallery_categories_slug", "slug", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    images: Mapped[list["GalleryImage"]] = relationship(back_populates="category")

    def to_dict(self, *, image_count: int | None = None) -> dict:
        data = {
            "id": self.id,
            "slug": self.slug,
            "name": self.name,
            "description": self.description,
            "position": self.position,
        }
        if image_count is not None:
            data["image_count"] = image_count
        return data


class GalleryImage(db.Model):
    __tablename__ = "gallery_images"
    __table_args__ = (
        Index("ix_gallery_images_category_position", "category_id", "position"),
        Index("ix_gallery_images_featured", "is_featured"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # A deleted category leaves its images in place, uncategorised.
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("gallery_categories.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Required by the spec: no image enters the gallery without real alt text.
    alt_text: Mapped[str] = mapped_column(String(300), nullable=False)
    url: Mapped[str] = mapped_column(String(600), nullable=False)
    thumb_url: Mapped[str | None] = mapped_column(String(600), nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    is_featured: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False,
                                              server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )

    category: Mapped[GalleryCategory | None] = relationship(back_populates="images")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "alt_text": self.alt_text,
            "url": self.url,
            "thumb_url": self.thumb_url,
            "width": self.width,
            "height": self.height,
            "position": self.position,
            "is_featured": self.is_featured,
            "created_at": iso(self.created_at),
            "category": (
                {
                    "id": self.category.id,
                    "slug": self.category.slug,
                    "name": self.category.name,
                }
                if self.category is not None
                else None
            ),
        }

    def to_admin_dict(self) -> dict:
        data = self.to_dict()
        data["category_id"] = self.category_id
        data["storage_key"] = self.storage_key
        return data
