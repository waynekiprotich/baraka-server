"""Event queries and mutations."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from ..errors import ConflictError, NotFoundError, ValidationError
from ..extensions import db
from ..models import Event, utcnow
from ..slugs import unique_slug
from . import paginate

EDITABLE_FIELDS = {
    "title",
    "slug",
    "summary",
    "description",
    "starts_at",
    "ends_at",
    "location",
    "cover_image_url",
    "is_published",
}


def list_public(page: int, per_page: int, upcoming: bool | None = None):
    stmt = select(Event).where(Event.is_published.is_(True))
    if upcoming is True:
        stmt = stmt.where(Event.starts_at >= utcnow()).order_by(Event.starts_at.asc())
    elif upcoming is False:
        stmt = stmt.where(Event.starts_at < utcnow()).order_by(Event.starts_at.desc())
    else:
        stmt = stmt.order_by(Event.starts_at.desc())
    rows, envelope = paginate(stmt, page, per_page)
    envelope["items"] = [row.to_public_dict() for row in rows]
    return envelope


def get_public_by_slug(slug: str) -> Event:
    stmt = select(Event).where(Event.is_published.is_(True), Event.slug == slug)
    event = db.session.execute(stmt).scalar_one_or_none()
    if event is None:
        raise NotFoundError("That event does not exist.")
    return event


def list_admin(page: int, per_page: int, published: bool | None = None,
               search: str | None = None):
    stmt = select(Event)
    if published is not None:
        stmt = stmt.where(Event.is_published.is_(published))
    if search:
        stmt = stmt.where(func.lower(Event.title).like(f"%{search.lower()}%"))
    stmt = stmt.order_by(Event.starts_at.desc(), Event.id.desc())
    rows, envelope = paginate(stmt, page, per_page)
    envelope["items"] = [row.to_admin_dict() for row in rows]
    return envelope


def get_admin(event_id: int) -> Event:
    event = db.session.get(Event, event_id)
    if event is None:
        raise NotFoundError("That event does not exist.")
    return event


def create(data: dict) -> Event:
    event = Event(
        title=data["title"],
        starts_at=data["starts_at"],
        description=data.get("description") or "",
    )
    _apply(event, data, is_new=True)
    db.session.add(event)
    _commit()
    return event


def update(event: Event, data: dict) -> Event:
    _apply(event, data, is_new=False)
    _commit()
    return event


def set_published(event: Event, is_published: bool) -> Event:
    event.is_published = is_published
    _commit()
    return event


def delete(event: Event) -> None:
    db.session.delete(event)
    _commit()


def _apply(event: Event, data: dict, *, is_new: bool) -> None:
    if "slug" in data and data["slug"]:
        event.slug = unique_slug(
            Event, data["slug"], exclude_id=None if is_new else event.id, fallback="event"
        )
    elif is_new:
        event.slug = unique_slug(Event, data.get("title") or event.title, fallback="event")

    for field in ("title", "summary", "description", "location", "cover_image_url"):
        if field in data:
            event.__setattr__(field, data[field])
    if "starts_at" in data and data["starts_at"] is not None:
        event.starts_at = data["starts_at"]
    if "ends_at" in data:
        event.ends_at = data["ends_at"]
    if "is_published" in data:
        event.is_published = data["is_published"]
    if event.description is None:
        event.description = ""

    if event.ends_at is not None and event.starts_at is not None and event.ends_at < event.starts_at:
        raise ValidationError(
            "Some fields need attention.",
            fields={"ends_at": "The end time must not be before the start time."},
        )


def _commit() -> None:
    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        raise ConflictError("An event with that slug already exists.") from exc
