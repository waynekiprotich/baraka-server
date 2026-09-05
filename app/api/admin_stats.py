"""Dashboard counts. Every number here has a query behind it."""

from __future__ import annotations

from flask import Blueprint, jsonify
from sqlalchemy import func, select

from ..extensions import db
from ..models import Enquiry, Event, GalleryCategory, GalleryImage, NewsArticle, utcnow
from ..security import admin_required

bp = Blueprint("admin_stats", __name__)


def _count(model, *conditions) -> int:
    stmt = select(func.count()).select_from(model)
    if conditions:
        stmt = stmt.where(*conditions)
    return db.session.execute(stmt).scalar_one()


@bp.get("/admin/stats")
@admin_required()
def stats():
    now = utcnow()
    news_total = _count(NewsArticle)
    news_published = _count(NewsArticle, NewsArticle.is_published.is_(True))
    events_total = _count(Event)
    events_published = _count(Event, Event.is_published.is_(True))

    recent_enquiries = (
        db.session.execute(
            select(Enquiry).order_by(Enquiry.created_at.desc(), Enquiry.id.desc()).limit(5)
        )
        .scalars()
        .all()
    )

    return jsonify(
        {
            "news": {
                "total": news_total,
                "published": news_published,
                "draft": news_total - news_published,
            },
            "events": {
                "total": events_total,
                "published": events_published,
                "draft": events_total - events_published,
                "upcoming": _count(
                    Event, Event.is_published.is_(True), Event.starts_at >= now
                ),
            },
            "gallery": {
                "images": _count(GalleryImage),
                "categories": _count(GalleryCategory),
                "featured": _count(GalleryImage, GalleryImage.is_featured.is_(True)),
            },
            "enquiries": {
                "total": _count(Enquiry),
                "new": _count(Enquiry, Enquiry.status == "new"),
                "read": _count(Enquiry, Enquiry.status == "read"),
                "archived": _count(Enquiry, Enquiry.status == "archived"),
            },
            "recent_enquiries": [enquiry.to_dict() for enquiry in recent_enquiries],
        }
    ), 200
