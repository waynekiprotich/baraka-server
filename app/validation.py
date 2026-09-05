"""Hand-rolled request validation.

No schema library. A `Payload` collects every problem it finds, rejects unknown
fields, and distinguishes an absent key from an explicit null so a PUT can
clear a nullable column without every other column being wiped.

Usage:

    body = Payload(json_body(), allowed={"title", "body"})
    title = body.string("title", required=True, max_length=200)
    data = body.done()          # raises ValidationError with a fields map
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone

from flask import request

from .errors import ValidationError

# Sentinel meaning "the client did not send this key at all".
MISSING = object()

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$")
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_URL_RE = re.compile(r"^(https?://|/)[^\s]*$")
_PHONE_RE = re.compile(r"^[0-9+()\-.\s]{7,40}$")

TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off"}


def json_body(required: bool = True) -> dict:
    """Return the request's JSON object, or raise a clean validation error."""
    data = request.get_json(silent=True)
    if data is None:
        if required:
            raise ValidationError("A JSON request body is required.")
        return {}
    if not isinstance(data, dict):
        raise ValidationError("The request body must be a JSON object.")
    return data


def iso(value: datetime | date | None) -> str | None:
    """Serialise a datetime as ISO 8601 UTC with a trailing Z."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return value.isoformat()


def parse_datetime(raw: str) -> datetime:
    """Parse an ISO 8601 string into an aware UTC datetime."""
    text = raw.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_bool(raw) -> bool | None:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        lowered = raw.strip().lower()
        if lowered in TRUE_VALUES:
            return True
        if lowered in FALSE_VALUES:
            return False
    return None


class Payload:
    """Validates one JSON object, accumulating field errors."""

    def __init__(self, data: dict, allowed: set[str] | None = None):
        self.data = data if isinstance(data, dict) else {}
        self.errors: dict[str, str] = {}
        self.cleaned: dict[str, object] = {}
        if allowed is not None:
            for key in self.data:
                if key not in allowed:
                    self.errors[key] = "Unknown field."

    # -- internals ---------------------------------------------------------

    def _raw(self, name: str):
        return self.data.get(name, MISSING)

    def _fail(self, name: str, message: str):
        self.errors.setdefault(name, message)
        return MISSING

    def _accept(self, name: str, value):
        self.cleaned[name] = value
        return value

    def _absent(self, name: str, required: bool, default):
        if required:
            return self._fail(name, "This field is required.")
        if default is not MISSING:
            return self._accept(name, default)
        return MISSING

    # -- field types -------------------------------------------------------

    def string(
        self,
        name: str,
        *,
        required: bool = False,
        default=MISSING,
        min_length: int = 1,
        max_length: int = 255,
        nullable: bool = False,
        strip: bool = True,
    ):
        raw = self._raw(name)
        if raw is MISSING:
            return self._absent(name, required, default)
        if raw is None:
            if nullable:
                return self._accept(name, None)
            return self._fail(name, "This field may not be null.")
        if not isinstance(raw, str):
            return self._fail(name, "Must be text.")
        value = raw.strip() if strip else raw
        if not value:
            if nullable:
                return self._accept(name, None)
            if required or min_length > 0:
                return self._fail(name, "This field is required.")
            return self._accept(name, value)
        if len(value) < min_length:
            return self._fail(name, f"Must be at least {min_length} characters.")
        if len(value) > max_length:
            return self._fail(name, f"Must be {max_length} characters or fewer.")
        return self._accept(name, value)

    def text(self, name: str, *, required: bool = False, default=MISSING,
             max_length: int = 20000, nullable: bool = False):
        return self.string(
            name,
            required=required,
            default=default,
            min_length=1 if required else 0,
            max_length=max_length,
            nullable=nullable,
        )

    def email(self, name: str, *, required: bool = False, default=MISSING):
        value = self.string(name, required=required, default=default, max_length=255)
        if value is MISSING or value is None or name in self.errors:
            return value
        lowered = value.lower()
        if not _EMAIL_RE.match(lowered):
            return self._fail(name, "Enter a valid email address.")
        return self._accept(name, lowered)

    def phone(self, name: str, *, required: bool = False, default=MISSING, nullable: bool = True):
        value = self.string(name, required=required, default=default, max_length=40,
                            nullable=nullable, min_length=0)
        if value is MISSING or value is None or name in self.errors or value == "":
            return value
        if not _PHONE_RE.match(value):
            return self._fail(name, "Enter a valid phone number.")
        return value

    def url(self, name: str, *, required: bool = False, default=MISSING,
            nullable: bool = True, max_length: int = 600):
        value = self.string(name, required=required, default=default, nullable=nullable,
                            min_length=0, max_length=max_length)
        if value is MISSING or value is None or name in self.errors or value == "":
            return value
        if not _URL_RE.match(value):
            return self._fail(name, "Must be an http(s) or root-relative URL.")
        return value

    def slug(self, name: str, *, required: bool = False, default=MISSING,
             nullable: bool = True, max_length: int = 200):
        value = self.string(name, required=required, default=default, nullable=nullable,
                            min_length=0, max_length=max_length)
        if value is MISSING or value is None or name in self.errors or value == "":
            return value
        lowered = value.lower()
        if not _SLUG_RE.match(lowered):
            return self._fail(name, "Use lowercase letters, numbers and hyphens only.")
        return self._accept(name, lowered)

    def boolean(self, name: str, *, required: bool = False, default=MISSING):
        raw = self._raw(name)
        if raw is MISSING:
            return self._absent(name, required, default)
        parsed = parse_bool(raw)
        if parsed is None:
            return self._fail(name, "Must be true or false.")
        return self._accept(name, parsed)

    def integer(self, name: str, *, required: bool = False, default=MISSING,
                minimum: int | None = None, maximum: int | None = None,
                nullable: bool = False):
        raw = self._raw(name)
        if raw is MISSING:
            return self._absent(name, required, default)
        if raw is None:
            if nullable:
                return self._accept(name, None)
            return self._fail(name, "This field may not be null.")
        if isinstance(raw, bool) or not isinstance(raw, (int, str)):
            return self._fail(name, "Must be a whole number.")
        try:
            value = int(str(raw).strip())
        except ValueError:
            return self._fail(name, "Must be a whole number.")
        if minimum is not None and value < minimum:
            return self._fail(name, f"Must be {minimum} or more.")
        if maximum is not None and value > maximum:
            return self._fail(name, f"Must be {maximum} or less.")
        return self._accept(name, value)

    def enum(self, name: str, choices, *, required: bool = False, default=MISSING,
             nullable: bool = False):
        raw = self._raw(name)
        if raw is MISSING:
            return self._absent(name, required, default)
        if raw is None:
            if nullable:
                return self._accept(name, None)
            return self._fail(name, "This field may not be null.")
        if not isinstance(raw, str) or raw not in choices:
            return self._fail(name, "Must be one of: " + ", ".join(choices) + ".")
        return self._accept(name, raw)

    def datetime_(self, name: str, *, required: bool = False, default=MISSING,
                  nullable: bool = True):
        raw = self._raw(name)
        if raw is MISSING:
            return self._absent(name, required, default)
        if raw is None or raw == "":
            if nullable:
                return self._accept(name, None)
            return self._fail(name, "This field is required.")
        if not isinstance(raw, str):
            return self._fail(name, "Must be an ISO 8601 date-time string.")
        try:
            return self._accept(name, parse_datetime(raw))
        except ValueError:
            return self._fail(name, "Must be an ISO 8601 date-time string.")

    def int_list(self, name: str, *, required: bool = False, default=MISSING,
                 max_items: int = 500):
        raw = self._raw(name)
        if raw is MISSING:
            return self._absent(name, required, default)
        if not isinstance(raw, list):
            return self._fail(name, "Must be a list of ids.")
        if len(raw) > max_items:
            return self._fail(name, f"No more than {max_items} items.")
        values: list[int] = []
        for item in raw:
            if isinstance(item, bool) or not isinstance(item, (int, str)):
                return self._fail(name, "Every id must be a whole number.")
            try:
                values.append(int(str(item).strip()))
            except ValueError:
                return self._fail(name, "Every id must be a whole number.")
        if len(set(values)) != len(values):
            return self._fail(name, "Ids must be unique.")
        return self._accept(name, values)

    def object_of_strings(self, name: str, *, required: bool = False,
                          max_keys: int = 200, max_value_length: int = 20000):
        raw = self._raw(name)
        if raw is MISSING:
            return self._absent(name, required, MISSING)
        if not isinstance(raw, dict):
            return self._fail(name, "Must be an object of key/value pairs.")
        if len(raw) > max_keys:
            return self._fail(name, f"No more than {max_keys} keys.")
        cleaned: dict[str, str] = {}
        for key, value in raw.items():
            if not isinstance(key, str) or not key.strip():
                return self._fail(name, "Every key must be a non-empty string.")
            if value is None:
                cleaned[key.strip()] = ""
                continue
            if isinstance(value, bool):
                cleaned[key.strip()] = "true" if value else "false"
                continue
            if isinstance(value, (int, float)):
                cleaned[key.strip()] = str(value)
                continue
            if not isinstance(value, str):
                return self._fail(name, f"Value for '{key}' must be text.")
            if len(value) > max_value_length:
                return self._fail(name, f"Value for '{key}' is too long.")
            cleaned[key.strip()] = value.strip()
        return self._accept(name, cleaned)

    # -- finishing ---------------------------------------------------------

    def has(self, name: str) -> bool:
        """True when the client sent the key at all (even as null)."""
        return name in self.data

    def done(self) -> dict:
        if self.errors:
            raise ValidationError("Some fields need attention.", fields=self.errors)
        return self.cleaned


# --- query-string helpers -------------------------------------------------


def query_int(name: str, default: int, *, minimum: int = 1, maximum: int = 1000) -> int:
    raw = request.args.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ValidationError(
            "Some fields need attention.", fields={name: "Must be a whole number."}
        ) from None
    return max(minimum, min(maximum, value))


def query_bool(name: str, default: bool | None = None) -> bool | None:
    raw = request.args.get(name)
    if raw is None or not raw.strip():
        return default
    parsed = parse_bool(raw)
    if parsed is None:
        raise ValidationError(
            "Some fields need attention.", fields={name: "Must be true or false."}
        )
    return parsed


def query_str(name: str, *, max_length: int = 200) -> str | None:
    raw = request.args.get(name)
    if raw is None:
        return None
    value = raw.strip()
    if not value:
        return None
    if len(value) > max_length:
        raise ValidationError(
            "Some fields need attention.",
            fields={name: f"Must be {max_length} characters or fewer."},
        )
    return value


def pagination() -> tuple[int, int]:
    """(page, per_page) from the query string, clamped to sane bounds."""
    return query_int("page", 1, minimum=1, maximum=100000), query_int(
        "per_page", 12, minimum=1, maximum=100
    )
