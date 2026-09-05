"""Public news endpoints."""

from __future__ import annotations

from flask import Blueprint, jsonify

from ..services import news_service
from ..validation import pagination, query_str

bp = Blueprint("news", __name__)


@bp.get("/news")
def list_news():
    page, per_page = pagination()
    return jsonify(
        news_service.list_public(
            page, per_page, category=query_str("category", max_length=80), search=query_str("q")
        )
    ), 200


@bp.get("/news/categories")
def news_categories():
    return jsonify({"items": news_service.public_categories()}), 200


@bp.get("/news/<slug>")
def news_detail(slug: str):
    article = news_service.get_public_by_slug(slug)
    return jsonify(article.to_public_dict(include_body=True)), 200
