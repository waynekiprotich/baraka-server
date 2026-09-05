"""Admin news CRUD."""

from __future__ import annotations

from flask import Blueprint, jsonify

from ..security import admin_required
from ..services import news_service
from ..validation import Payload, json_body, pagination, query_bool, query_str

bp = Blueprint("admin_news", __name__)

ALLOWED = news_service.EDITABLE_FIELDS


def _validate(raw: dict, *, is_new: bool) -> dict:
    body = Payload(raw, allowed=ALLOWED)
    body.string("title", required=is_new, max_length=200)
    body.slug("slug", nullable=True)
    body.string("excerpt", max_length=300, nullable=True, min_length=0)
    body.text("body", max_length=60000, nullable=True)
    body.string("category", max_length=80, nullable=True, min_length=0)
    body.url("cover_image_url")
    body.string("cover_image_alt", max_length=300, nullable=True, min_length=0)
    body.string("author", max_length=120, nullable=True, min_length=0)
    body.boolean("is_published", default=False if is_new else None)
    body.datetime_("published_at")
    data = body.done()
    if not is_new:
        # Only what the client actually sent may change.
        data = {key: value for key, value in data.items() if key in raw}
    return data


@bp.get("/admin/news")
@admin_required()
def list_news():
    page, per_page = pagination()
    return jsonify(
        news_service.list_admin(
            page, per_page, published=query_bool("published"), search=query_str("q")
        )
    ), 200


@bp.post("/admin/news")
@admin_required()
def create_news():
    data = _validate(json_body(), is_new=True)
    article = news_service.create(data)
    return jsonify(article.to_admin_dict()), 201


@bp.get("/admin/news/<int:article_id>")
@admin_required()
def get_news(article_id: int):
    return jsonify(news_service.get_admin(article_id).to_admin_dict()), 200


@bp.put("/admin/news/<int:article_id>")
@admin_required()
def update_news(article_id: int):
    article = news_service.get_admin(article_id)
    data = _validate(json_body(), is_new=False)
    return jsonify(news_service.update(article, data).to_admin_dict()), 200


@bp.patch("/admin/news/<int:article_id>/publish")
@admin_required()
def publish_news(article_id: int):
    article = news_service.get_admin(article_id)
    body = Payload(json_body(), allowed={"is_published"})
    body.boolean("is_published", required=True)
    data = body.done()
    return jsonify(news_service.set_published(article, data["is_published"]).to_admin_dict()), 200


@bp.delete("/admin/news/<int:article_id>")
@admin_required()
def delete_news(article_id: int):
    news_service.delete(news_service.get_admin(article_id))
    return "", 204
