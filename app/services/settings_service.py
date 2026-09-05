"""Site settings.

`DEFAULT_SETTINGS` is the canonical list of keys the site understands. `flask
seed` writes any that are missing (and never overwrites a value the school has
edited), and the admin PUT refuses keys that are not in this list -- so a typo
in the dashboard cannot silently create a setting nothing reads.

Values marked PLACEHOLDER below are deliberately empty: SPEC section 2 forbids
inventing facts, so the school fills them in from the dashboard and the
frontend renders an honest "not available yet" state until they do.
"""

from __future__ import annotations

from flask import current_app
from sqlalchemy import select

from ..errors import ValidationError
from ..extensions import db
from ..models import SiteSetting, utcnow

# key -> (default value, value_type, group, label)
DEFAULT_SETTINGS: dict[str, tuple[str, str, str, str]] = {
    # --- identity ---------------------------------------------------------
    "school_name": ("Baraka School Kapsabet", "string", "identity", "School name"),
    "tagline": (
        "Nurturing Excellence, Character & Future Leaders",
        "string",
        "identity",
        "Positioning line",
    ),
    "motto": ("“Baraka” — Blessing", "string", "identity", "Motto"),
    "curriculum": (
        "CBC (Competency-Based Curriculum), Playgroup to Grade 9",
        "string",
        "identity",
        "Curriculum",
    ),
    "founded_year": ("2011", "number", "identity", "Year founded"),
    "site_url": ("https://barakaschoolkapsabet.ac.ke", "url", "identity", "Public site URL"),
    "logo_url": ("/brand/crest-ink-512.png", "url", "identity", "Logo image"),
    # --- contact ----------------------------------------------------------
    "phone": ("+254 700 123456", "string", "contact", "Phone number (placeholder)"),
    "email": ("info@barakaschoolkapsabet.ac.ke", "string", "contact", "General email"),
    "admissions_email": (
        "admissions@barakaschoolkapsabet.ac.ke",
        "string",
        "contact",
        "Admissions email",
    ),
    "address_line1": ("Kapsabet–Eldoret Road", "string", "contact", "Address line 1"),
    "address_line2": ("Kapsabet, Nandi County", "string", "contact", "Address line 2"),
    "address_locality": ("Kapsabet", "string", "contact", "Town"),
    "address_region": ("Nandi County", "string", "contact", "County"),
    "address_country": ("Kenya", "string", "contact", "Country"),
    "geo_lat": ("0.2017", "number", "contact", "Latitude"),
    "geo_lng": ("35.1053", "number", "contact", "Longitude"),
    "map_url": (
        "https://www.google.com/maps/search/?api=1&query=0.2017,35.1053",
        "url",
        "contact",
        "Map link",
    ),
    # PLACEHOLDER: no embed URL has been supplied by the school.
    "map_embed_url": ("", "url", "contact", "Map embed URL (not yet supplied)"),
    # PLACEHOLDER: office hours were not supplied with the source content.
    "office_hours": ("", "text", "contact", "Office hours (not yet supplied)"),
    # --- social -----------------------------------------------------------
    "facebook_url": (
        "https://facebook.com/barakaschoolkapsabet",
        "url",
        "social",
        "Facebook page",
    ),
    "instagram_url": (
        "https://instagram.com/barakaschoolkapsabet",
        "url",
        "social",
        "Instagram profile",
    ),
    # PLACEHOLDER: the school video has not been supplied.
    "youtube_url": ("", "url", "social", "YouTube video (not yet supplied)"),
    # --- hero -------------------------------------------------------------
    "hero_title": (
        "Nurturing Excellence, Character & Future Leaders",
        "string",
        "hero",
        "Hero heading",
    ),
    "hero_subtitle": (
        "A premium private mixed day school in Kapsabet, Nandi County — CBC from "
        "Playgroup to Grade 9.",
        "text",
        "hero",
        "Hero subheading",
    ),
    # PLACEHOLDER: empty until a real school photograph is uploaded. The
    # frontend falls back to its own curated hero image while this is blank.
    "hero_image_url": ("", "url", "hero", "Hero image (not yet supplied)"),
    "hero_image_alt": (
        "Baraka School Kapsabet learners on the school grounds",
        "string",
        "hero",
        "Hero image alt text",
    ),
    # --- stats ------------------------------------------------------------
    "stat_learners": ("640+", "string", "stats", "Current learners"),
    "stat_staff": ("58+", "string", "stats", "Teaching staff"),
    "stat_years": ("15+", "string", "stats", "Years running"),
    "stat_transition": ("98%", "string", "stats", "KCPE mean transition"),
    "stat_distinction": ("72%", "string", "stats", "Distinction rate"),
    "stat_top_performers": ("9", "string", "stats", "County top performers"),
    "stat_ratio": ("1:18", "string", "stats", "Teacher–learner ratio"),
    "stat_class_cap": ("24", "string", "stats", "Lower Primary class cap"),
    # --- admissions -------------------------------------------------------
    "admissions_open_text": (
        "Places are open for Playgroup through Grade 9 for the 2027 intake.",
        "text",
        "admissions",
        "Admissions status line",
    ),
    # PLACEHOLDER: downloadable documents have not been supplied.
    "application_form_url": (
        "",
        "url",
        "admissions",
        "Application form PDF (not yet supplied)",
    ),
    "fee_structure_url": ("", "url", "admissions", "Fee structure PDF (not yet supplied)"),
    "academic_calendar_url": (
        "",
        "url",
        "admissions",
        "Academic calendar PDF (not yet supplied)",
    ),
    "virtual_tour_url": ("", "url", "admissions", "360° virtual tour (not yet supplied)"),
}


def all_settings() -> list[SiteSetting]:
    return list(
        db.session.execute(
            select(SiteSetting).order_by(SiteSetting.group, SiteSetting.key)
        ).scalars().all()
    )


def public_map() -> dict[str, str]:
    """Flat {key: value} for the public site -- public groups only."""
    groups = set(current_app.config["PUBLIC_SETTING_GROUPS"])
    stmt = select(SiteSetting).where(SiteSetting.group.in_(groups)).order_by(SiteSetting.key)
    return {row.key: row.value for row in db.session.execute(stmt).scalars().all()}


def admin_list() -> list[dict]:
    return [row.to_dict() for row in all_settings()]


def update_many(values: dict[str, str]) -> list[dict]:
    """Write a {key: value} map. Unknown keys are rejected, not created."""
    unknown = sorted(key for key in values if key not in DEFAULT_SETTINGS)
    if unknown:
        raise ValidationError(
            "Some fields need attention.",
            fields={key: "Unknown setting." for key in unknown},
        )
    existing = {row.key: row for row in all_settings()}
    now = utcnow()
    for key, value in values.items():
        row = existing.get(key)
        if row is None:
            default_value, value_type, group, label = DEFAULT_SETTINGS[key]
            row = SiteSetting(key=key, value_type=value_type, group=group, label=label)
            db.session.add(row)
            existing[key] = row
        row.value = value
        row.updated_at = now
    db.session.commit()
    return admin_list()


def ensure_defaults() -> int:
    """Create any missing setting rows. Idempotent; never overwrites a value."""
    existing = {row.key for row in all_settings()}
    created = 0
    for key, (value, value_type, group, label) in DEFAULT_SETTINGS.items():
        if key in existing:
            continue
        db.session.add(
            SiteSetting(key=key, value=value, value_type=value_type, group=group, label=label)
        )
        created += 1
    if created:
        db.session.commit()
    return created
