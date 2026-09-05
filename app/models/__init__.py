"""SQLAlchemy models.

Imported as a package so Alembic's autogenerate sees every table.
"""

from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Timezone-aware "now", used as the Python-side default for timestamps."""
    return datetime.now(timezone.utc)


from .admin_user import AdminUser  # noqa: E402
from .enquiry import ENQUIRY_SOURCES, ENQUIRY_STATUSES, Enquiry  # noqa: E402
from .event import Event  # noqa: E402
from .gallery import GalleryCategory, GalleryImage  # noqa: E402
from .news import NewsArticle  # noqa: E402
from .setting import SETTING_VALUE_TYPES, SiteSetting  # noqa: E402
from .system import RateLimitHit, TokenBlocklist  # noqa: E402

__all__ = [
    "AdminUser",
    "Enquiry",
    "ENQUIRY_SOURCES",
    "ENQUIRY_STATUSES",
    "Event",
    "GalleryCategory",
    "GalleryImage",
    "NewsArticle",
    "RateLimitHit",
    "SETTING_VALUE_TYPES",
    "SiteSetting",
    "TokenBlocklist",
    "utcnow",
]
