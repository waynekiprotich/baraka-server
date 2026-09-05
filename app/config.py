"""Application configuration.

Every setting is read from the environment with a sensible local default so a
fresh checkout runs without a .env file. Secrets have no usable default outside
development -- create_app() refuses to boot with the development placeholder
when FLASK_ENV is not "development".
"""

from __future__ import annotations

import getpass
import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

# The placeholder used when no secret is configured. Checked for by name in
# create_app() so a production boot with an unset secret fails loudly.
DEV_PLACEHOLDER_SECRET = "dev-only-insecure-secret-change-me"


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _default_database_url(database: str) -> str:
    user = os.environ.get("PGUSER") or getpass.getuser()
    host = os.environ.get("PGHOST", "localhost")
    port = os.environ.get("PGPORT", "5432")
    return f"postgresql+psycopg://{user}@{host}:{port}/{database}"


def _resolve_upload_dir(value: str | None, default: Path) -> Path:
    """Always return an absolute path, regardless of what was configured.

    `UPLOAD_DIR=uploads` in .env.example is a *relative* value. Every other use of it
    in this app (writing a file, checking `.is_file()`) resolves relative paths against
    the process's working directory, which happens to be `server/` when run normally --
    but Werkzeug's `send_from_directory()` resolves a relative directory against
    `app.root_path` (`server/app/`) instead, one level too deep. A relative UPLOAD_DIR
    therefore writes files correctly and then 404s on every request to serve them back.
    Resolving here, once, against this file's own directory removes that ambiguity for
    every caller.
    """
    path = Path(value) if value else default
    return path if path.is_absolute() else (BASE_DIR / path)


class Config:
    """Base configuration -- production defaults."""

    ENV_NAME = "production"
    DEBUG = False
    TESTING = False

    SECRET_KEY = os.environ.get("SECRET_KEY", DEV_PLACEHOLDER_SECRET)

    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or _default_database_url("baraka")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 900}

    # --- auth -------------------------------------------------------------
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY") or SECRET_KEY
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=_env_int("JWT_ACCESS_MINUTES", 30))
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=_env_int("JWT_REFRESH_DAYS", 14))
    JWT_ERROR_MESSAGE_KEY = "message"
    PASSWORD_MIN_LENGTH = 10

    # --- uploads ----------------------------------------------------------
    UPLOAD_DIR = _resolve_upload_dir(os.environ.get("UPLOAD_DIR"), BASE_DIR / "uploads")
    MAX_UPLOAD_BYTES = _env_int("MAX_UPLOAD_BYTES", 8 * 1024 * 1024)
    # Leave room for the multipart envelope so an 8 MB file reaches our own
    # size check (and a clear PAYLOAD_TOO_LARGE) rather than Werkzeug's.
    MAX_CONTENT_LENGTH = MAX_UPLOAD_BYTES + 512 * 1024
    UPLOAD_MAX_EDGE = 2000
    UPLOAD_THUMB_EDGE = 480
    UPLOAD_ALLOWED_FORMATS = ("JPEG", "PNG", "WEBP")

    # --- Supabase Storage ---------------------------------------------------
    # Server-side only -- the service-role key is never sent to the frontend.
    # When unset, uploads fall back to local disk (see TestConfig, and a fresh
    # checkout with no .env yet).
    SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
    SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    SUPABASE_STORAGE_BUCKET = os.environ.get("SUPABASE_STORAGE_BUCKET", "images")

    # --- ImageKit ------------------------------------------------------------
    # Server-side only -- the private key is never sent to the frontend. When
    # configured, this takes priority over Supabase Storage (see image_service.py);
    # falls back to Supabase Storage, then local disk, when unset.
    IMAGEKIT_PUBLIC_KEY = os.environ.get("IMAGEKIT_PUBLIC_KEY", "")
    IMAGEKIT_PRIVATE_KEY = os.environ.get("IMAGEKIT_PRIVATE_KEY", "")
    IMAGEKIT_URL_ENDPOINT = os.environ.get("IMAGEKIT_URL_ENDPOINT", "")

    # --- CORS -------------------------------------------------------------
    CORS_ORIGINS = [
        origin.strip()
        for origin in os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",")
        if origin.strip()
    ]
    CORS_MAX_AGE = _env_int("CORS_MAX_AGE", 600)

    # --- rate limiting ----------------------------------------------------
    # bucket -> (max attempts, window in seconds)
    RATE_LIMITS = {
        "auth_login": (5, 15 * 60),
        "enquiry_create": (5, 60 * 60),
    }
    # Number of proxies actually in front of the app. Trusting more hops than
    # exist would let a caller forge their IP through X-Forwarded-For.
    TRUSTED_PROXY_HOPS = _env_int("TRUSTED_PROXY_HOPS", 0)
    IP_HASH_SALT = os.environ.get("IP_HASH_SALT", "baraka-ip-salt")

    # --- caching ----------------------------------------------------------
    PUBLIC_CACHE_CONTROL = "public, max-age=60, stale-while-revalidate=300"
    IMMUTABLE_CACHE_CONTROL = "public, max-age=31536000, immutable"
    GZIP_MIN_BYTES = 1024

    # Setting groups exposed by the public GET /api/v1/settings endpoint.
    PUBLIC_SETTING_GROUPS = ("identity", "contact", "social", "hero", "stats", "admissions")


class DevConfig(Config):
    ENV_NAME = "development"
    DEBUG = True


class TestConfig(Config):
    ENV_NAME = "testing"
    TESTING = True
    DEBUG = False
    # 48 bytes: long enough that PyJWT does not warn about the HMAC key length.
    SECRET_KEY = "baraka-testing-secret-not-used-outside-the-suite"
    JWT_SECRET_KEY = "baraka-testing-secret-not-used-outside-the-suite"
    SQLALCHEMY_DATABASE_URI = os.environ.get("TEST_DATABASE_URL") or _default_database_url(
        "baraka_test"
    )
    UPLOAD_DIR = _resolve_upload_dir(os.environ.get("TEST_UPLOAD_DIR"), BASE_DIR / "uploads" / "_test")
    # The suite never talks to a real Supabase project -- uploads are local disk only,
    # regardless of what a developer's .env happens to have configured.
    SUPABASE_URL = ""
    SUPABASE_SERVICE_ROLE_KEY = ""
    SUPABASE_STORAGE_BUCKET = ""
    IMAGEKIT_PUBLIC_KEY = ""
    IMAGEKIT_PRIVATE_KEY = ""
    IMAGEKIT_URL_ENDPOINT = ""


CONFIGS = {
    "development": DevConfig,
    "testing": TestConfig,
    "production": Config,
}


def resolve_config(name: str | None = None) -> type[Config]:
    key = (name or os.environ.get("FLASK_ENV") or "development").strip().lower()
    return CONFIGS.get(key, DevConfig)
