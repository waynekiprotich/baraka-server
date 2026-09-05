"""News article queries and mutations."""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from ..errors import ConflictError, NotFoundError
from ..extensions import db
from ..models import NewsArticle, utcnow
from ..slugs import unique_slug
from . import paginate

EDITABLE_FIELDS = {
    "title",
    "slug",
    "excerpt",
    "body",
    "category",
    "cover_image_url",
    "cover_image_alt",
    "author",
    "is_published",
    "published_at",
}


def _published_filter(stmt):
    return stmt.where(NewsArticle.is_published.is_(True))


def list_public(page: int, per_page: int, category: str | None = None, search: str | None = None):
    stmt = _published_filter(select(NewsArticle))
    if category:
        stmt = stmt.where(func.lower(NewsArticle.category) == category.lower())
    if search:
        pattern = f"%{search.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(NewsArticle.title).like(pattern),
                func.lower(NewsArticle.excerpt).like(pattern),
                func.lower(NewsArticle.body).like(pattern),
            )
        )
    stmt = stmt.order_by(NewsArticle.published_at.desc().nullslast(), NewsArticle.id.desc())
    rows, envelope = paginate(stmt, page, per_page)
    envelope["items"] = [row.to_public_dict() for row in rows]
    return envelope


def get_public_by_slug(slug: str) -> NewsArticle:
    stmt = _published_filter(select(NewsArticle)).where(NewsArticle.slug == slug)
    article = db.session.execute(stmt).scalar_one_or_none()
    if article is None:
        raise NotFoundError("That article does not exist.")
    return article


def public_categories() -> list[str]:
    stmt = (
        select(NewsArticle.category)
        .where(NewsArticle.is_published.is_(True), NewsArticle.category.is_not(None))
        .distinct()
        .order_by(NewsArticle.category)
    )
    return [row for row in db.session.execute(stmt).scalars().all() if row]


def list_admin(page: int, per_page: int, published: bool | None = None,
               search: str | None = None):
    stmt = select(NewsArticle)
    if published is not None:
        stmt = stmt.where(NewsArticle.is_published.is_(published))
    if search:
        pattern = f"%{search.lower()}%"
        stmt = stmt.where(func.lower(NewsArticle.title).like(pattern))
    stmt = stmt.order_by(NewsArticle.created_at.desc(), NewsArticle.id.desc())
    rows, envelope = paginate(stmt, page, per_page)
    envelope["items"] = [row.to_admin_dict() for row in rows]
    return envelope


def get_admin(article_id: int) -> NewsArticle:
    article = db.session.get(NewsArticle, article_id)
    if article is None:
        raise NotFoundError("That article does not exist.")
    return article


def create(data: dict) -> NewsArticle:
    article = NewsArticle(title=data["title"], body=data.get("body") or "")
    _apply(article, data, is_new=True)
    db.session.add(article)
    _commit()
    return article


def update(article: NewsArticle, data: dict) -> NewsArticle:
    _apply(article, data, is_new=False)
    _commit()
    return article


def set_published(article: NewsArticle, is_published: bool) -> NewsArticle:
    article.is_published = is_published
    if is_published and article.published_at is None:
        article.published_at = utcnow()
    _commit()
    return article


def delete(article: NewsArticle) -> None:
    db.session.delete(article)
    _commit()


def _apply(article: NewsArticle, data: dict, *, is_new: bool) -> None:
    if "slug" in data and data["slug"]:
        article.slug = unique_slug(
            NewsArticle, data["slug"], exclude_id=None if is_new else article.id, fallback="article"
        )
    elif is_new or ("title" in data and not getattr(article, "slug", None)):
        source = data.get("title") or article.title
        article.slug = unique_slug(
            NewsArticle, source, exclude_id=None if is_new else article.id, fallback="article"
        )

    for field in ("title", "excerpt", "body", "category", "cover_image_url",
                  "cover_image_alt", "author"):
        if field in data:
            article.__setattr__(field, data[field])

    if "is_published" in data:
        article.is_published = data["is_published"]
    if "published_at" in data:
        article.published_at = data["published_at"]
    if article.is_published and article.published_at is None:
        article.published_at = utcnow()
    if article.body is None:
        article.body = ""


def _commit() -> None:
    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        raise ConflictError("An article with that slug already exists.") from exc
