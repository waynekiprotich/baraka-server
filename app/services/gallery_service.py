"""Gallery categories and images."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from ..errors import ConflictError, NotFoundError, ValidationError
from ..extensions import db
from ..models import GalleryCategory, GalleryImage
from ..slugs import unique_slug
from . import paginate

CATEGORY_FIELDS = {"name", "slug", "description", "position"}
IMAGE_FIELDS = {
    "category_id",
    "title",
    "alt_text",
    "url",
    "thumb_url",
    "storage_key",
    "width",
    "height",
    "position",
    "is_featured",
}


# --- categories -----------------------------------------------------------


def list_categories(*, with_counts: bool = True) -> list[dict]:
    counts: dict[int, int] = {}
    if with_counts:
        rows = db.session.execute(
            select(GalleryImage.category_id, func.count(GalleryImage.id)).group_by(
                GalleryImage.category_id
            )
        ).all()
        counts = {category_id: count for category_id, count in rows if category_id is not None}
    stmt = select(GalleryCategory).order_by(GalleryCategory.position.asc(), GalleryCategory.name)
    categories = db.session.execute(stmt).scalars().all()
    return [
        category.to_dict(image_count=counts.get(category.id, 0) if with_counts else None)
        for category in categories
    ]


def get_category(category_id: int) -> GalleryCategory:
    category = db.session.get(GalleryCategory, category_id)
    if category is None:
        raise NotFoundError("That gallery category does not exist.")
    return category


def get_category_by_slug(slug: str) -> GalleryCategory:
    category = db.session.execute(
        select(GalleryCategory).where(GalleryCategory.slug == slug)
    ).scalar_one_or_none()
    if category is None:
        raise NotFoundError("That gallery category does not exist.")
    return category


def create_category(data: dict) -> GalleryCategory:
    category = GalleryCategory(name=data["name"])
    _apply_category(category, data, is_new=True)
    db.session.add(category)
    _commit("A category with that slug already exists.")
    return category


def update_category(category: GalleryCategory, data: dict) -> GalleryCategory:
    _apply_category(category, data, is_new=False)
    _commit("A category with that slug already exists.")
    return category


def delete_category(category: GalleryCategory) -> None:
    # The FK is ON DELETE SET NULL: images survive, uncategorised.
    db.session.delete(category)
    _commit("That category could not be deleted.")


def _apply_category(category: GalleryCategory, data: dict, *, is_new: bool) -> None:
    if "slug" in data and data["slug"]:
        category.slug = unique_slug(
            GalleryCategory,
            data["slug"],
            exclude_id=None if is_new else category.id,
            fallback="category",
        )
    elif is_new:
        category.slug = unique_slug(
            GalleryCategory, data.get("name") or category.name, fallback="category"
        )
    for field in ("name", "description", "position"):
        if field in data:
            category.__setattr__(field, data[field])
    if category.position is None:
        category.position = 0


# --- images ---------------------------------------------------------------


def list_public_images(page: int, per_page: int, category_slug: str | None = None):
    stmt = select(GalleryImage)
    if category_slug:
        category = get_category_by_slug(category_slug)
        stmt = stmt.where(GalleryImage.category_id == category.id)
    stmt = stmt.order_by(GalleryImage.position.asc(), GalleryImage.id.desc())
    rows, envelope = paginate(stmt, page, per_page)
    envelope["items"] = [row.to_dict() for row in rows]
    return envelope


def list_admin_images(page: int, per_page: int, category_id: int | None = None):
    stmt = select(GalleryImage)
    if category_id is not None:
        stmt = stmt.where(GalleryImage.category_id == category_id)
    stmt = stmt.order_by(GalleryImage.position.asc(), GalleryImage.id.desc())
    rows, envelope = paginate(stmt, page, per_page)
    envelope["items"] = [row.to_admin_dict() for row in rows]
    return envelope


def get_image(image_id: int) -> GalleryImage:
    image = db.session.get(GalleryImage, image_id)
    if image is None:
        raise NotFoundError("That image does not exist.")
    return image


def create_image(data: dict) -> GalleryImage:
    image = GalleryImage(alt_text=data["alt_text"], url=data["url"])
    _apply_image(image, data)
    if image.position is None or image.position == 0:
        image.position = _next_position(image.category_id)
    db.session.add(image)
    _commit("That image could not be saved.")
    return image


def update_image(image: GalleryImage, data: dict) -> GalleryImage:
    _apply_image(image, data)
    _commit("That image could not be saved.")
    return image


def delete_image(image: GalleryImage) -> None:
    db.session.delete(image)
    _commit("That image could not be deleted.")


def reorder_images(ids: list[int]) -> list[dict]:
    """Write the given order as positions 1..n. Every id must exist."""
    if not ids:
        raise ValidationError(
            "Some fields need attention.", fields={"ids": "Provide at least one image id."}
        )
    images = (
        db.session.execute(select(GalleryImage).where(GalleryImage.id.in_(ids))).scalars().all()
    )
    found = {image.id: image for image in images}
    missing = [image_id for image_id in ids if image_id not in found]
    if missing:
        raise ValidationError(
            "Some fields need attention.",
            fields={"ids": f"Unknown image ids: {', '.join(str(i) for i in missing)}."},
        )
    for position, image_id in enumerate(ids, start=1):
        found[image_id].position = position
    _commit("The gallery order could not be saved.")
    return [found[image_id].to_admin_dict() for image_id in ids]


def _apply_image(image: GalleryImage, data: dict) -> None:
    if "category_id" in data:
        category_id = data["category_id"]
        if category_id is not None:
            get_category(category_id)
        image.category_id = category_id
    for field in ("title", "alt_text", "url", "thumb_url", "storage_key", "width",
                  "height", "position", "is_featured"):
        if field in data:
            image.__setattr__(field, data[field])
    if image.is_featured is None:
        image.is_featured = False


def _next_position(category_id: int | None) -> int:
    stmt = select(func.coalesce(func.max(GalleryImage.position), 0))
    if category_id is not None:
        stmt = stmt.where(GalleryImage.category_id == category_id)
    return db.session.execute(stmt).scalar_one() + 1


def _commit(message: str) -> None:
    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        raise ConflictError(message) from exc
