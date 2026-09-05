"""Slug generation.

`slugify` normalises arbitrary text; `unique_slug` finds a free variant by
appending -2, -3 and so on. The database still owns the guarantee -- every
sluggable table carries a UNIQUE constraint and the services retry once on the
integrity error a concurrent insert would cause.
"""

from __future__ import annotations

import re
import unicodedata

from sqlalchemy import select

from .extensions import db

_NON_WORD = re.compile(r"[^a-z0-9]+")
_EDGE_HYPHENS = re.compile(r"^-+|-+$")

MAX_SLUG_LENGTH = 180


def slugify(value: str, *, fallback: str = "item") -> str:
    """Turn arbitrary text into a lowercase hyphenated ASCII slug."""
    if not value:
        return fallback
    normalised = unicodedata.normalize("NFKD", value)
    ascii_only = normalised.encode("ascii", "ignore").decode("ascii").lower()
    hyphenated = _NON_WORD.sub("-", ascii_only)
    trimmed = _EDGE_HYPHENS.sub("", hyphenated)[:MAX_SLUG_LENGTH]
    trimmed = _EDGE_HYPHENS.sub("", trimmed)
    return trimmed or fallback


def unique_slug(model, value: str, *, exclude_id: int | None = None,
                fallback: str = "item") -> str:
    """A slug for `model` that no other row is using."""
    base = slugify(value, fallback=fallback)
    candidate = base
    suffix = 2
    while _slug_taken(model, candidate, exclude_id):
        tail = f"-{suffix}"
        candidate = f"{base[: MAX_SLUG_LENGTH - len(tail)]}{tail}"
        suffix += 1
    return candidate


def _slug_taken(model, candidate: str, exclude_id: int | None) -> bool:
    stmt = select(model.id).where(model.slug == candidate)
    if exclude_id is not None:
        stmt = stmt.where(model.id != exclude_id)
    return db.session.execute(stmt.limit(1)).first() is not None
