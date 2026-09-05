"""The versioned API blueprint.

Every feature module defines a plain blueprint with full sub-paths; they are
nested under `api_v1` so the /api/v1 prefix is declared exactly once.

The parent blueprint is built inside `register_api` rather than at import
time: a module-level blueprint can only be assembled once per process, which
would quietly break the factory the moment a second `create_app()` is needed
(the test suite builds two).
"""

from __future__ import annotations

from flask import Blueprint, jsonify
from sqlalchemy import text

from ..extensions import db


def health():
    """Liveness probe, including a round trip to PostgreSQL."""
    database_ok = True
    try:
        db.session.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 - the probe reports, it does not raise
        db.session.rollback()
        database_ok = False
    payload = {"status": "ok" if database_ok else "degraded", "database": database_ok}
    return jsonify(payload), (200 if database_ok else 503)


def register_api(app) -> None:
    from . import (
        admin_enquiries,
        admin_events,
        admin_gallery,
        admin_news,
        admin_settings,
        admin_stats,
        auth,
        enquiries,
        events,
        gallery,
        news,
        settings,
        uploads,
    )

    api_v1 = Blueprint("api_v1", __name__, url_prefix="/api/v1")
    api_v1.add_url_rule("/health", view_func=health, methods=["GET"])

    for module in (
        auth,
        news,
        events,
        gallery,
        settings,
        enquiries,
        admin_stats,
        admin_news,
        admin_events,
        admin_gallery,
        admin_settings,
        admin_enquiries,
        uploads,
    ):
        api_v1.register_blueprint(module.bp)

    app.register_blueprint(api_v1)
    # Served outside the versioned API: these are the file URLs stored in rows.
    app.register_blueprint(uploads.files_bp)
