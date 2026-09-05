"""Application factory for the Baraka School Kapsabet API."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from flask import Flask

from .config import DEV_PLACEHOLDER_SECRET, Config, resolve_config
from .errors import register_error_handlers
from .extensions import cors, db, jwt, migrate
from .security import register_jwt_callbacks, register_security


def create_app(config_object: type[Config] | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_object or resolve_config())

    _configure_logging(app)
    _guard_secrets(app)

    # Models must be imported before Migrate so autogenerate sees the tables.
    from . import models  # noqa: F401

    db.init_app(app)
    migrate.init_app(app, db, directory=str(Path(app.root_path).parent / "migrations"))
    jwt.init_app(app)
    cors.init_app(
        app,
        resources={r"/api/v1/*": {"origins": app.config["CORS_ORIGINS"]}},
        supports_credentials=False,
        max_age=app.config["CORS_MAX_AGE"],
        allow_headers=["Content-Type", "Authorization", "X-Request-Id"],
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    )

    register_jwt_callbacks(jwt)
    register_security(app)
    register_error_handlers(app)

    from .api import register_api

    register_api(app)

    from .cli import register_cli

    register_cli(app)

    Path(app.config["UPLOAD_DIR"]).mkdir(parents=True, exist_ok=True)

    return app


def _configure_logging(app: Flask) -> None:
    level = logging.DEBUG if app.config.get("DEBUG") else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    app.logger.setLevel(level)


def _guard_secrets(app: Flask) -> None:
    """Refuse to boot in production with the development placeholder secret."""
    if app.config["ENV_NAME"] == "production":
        for key in ("SECRET_KEY", "JWT_SECRET_KEY"):
            if app.config.get(key) in (None, "", DEV_PLACEHOLDER_SECRET):
                raise RuntimeError(
                    f"{key} must be set to a real secret before running in production."
                )
        if "localhost:5173" in ",".join(app.config["CORS_ORIGINS"]):
            app.logger.warning(
                "CORS still allows the local dev origin; set CORS_ORIGINS for production."
            )


# `flask --app app run` and `flask db ...` both find this.
def _cli_app() -> Flask:  # pragma: no cover - used only by the flask CLI
    return create_app(resolve_config(os.environ.get("FLASK_ENV")))
