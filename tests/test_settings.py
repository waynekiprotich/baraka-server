"""Site settings: seeding, the public map, and the admin write path."""

from __future__ import annotations

from app.services import settings_service

from .conftest import error_of


def seed(app):
    return settings_service.ensure_defaults()


def test_ensure_defaults_creates_every_key_and_is_idempotent(app):
    created = seed(app)
    assert created == len(settings_service.DEFAULT_SETTINGS)
    assert seed(app) == 0


def test_the_keys_the_frontend_depends_on_all_exist(app, client):
    seed(app)
    values = client.get("/api/v1/settings").get_json()
    required = {
        "school_name",
        "tagline",
        "phone",
        "email",
        "admissions_email",
        "address_line1",
        "address_line2",
        "office_hours",
        "map_url",
        "facebook_url",
        "instagram_url",
        "hero_title",
        "hero_subtitle",
        "hero_image_url",
        "stat_learners",
        "stat_staff",
        "stat_years",
        "stat_transition",
        "stat_distinction",
        "stat_top_performers",
        "stat_ratio",
        "stat_class_cap",
        "admissions_open_text",
    }
    assert required <= set(values)


def test_the_public_endpoint_is_a_flat_string_map(app, client):
    seed(app)
    values = client.get("/api/v1/settings").get_json()
    assert values["school_name"] == "Baraka School Kapsabet"
    assert all(isinstance(value, str) for value in values.values())


def test_the_admin_endpoint_returns_rows_with_metadata(app, client, auth):
    seed(app)
    items = client.get("/api/v1/admin/settings", headers=auth).get_json()["items"]
    assert len(items) == len(settings_service.DEFAULT_SETTINGS)
    row = next(item for item in items if item["key"] == "school_name")
    assert set(row) == {"key", "value", "value_type", "group", "label", "updated_at"}


def test_put_updates_values_and_the_public_map_follows(app, client, auth):
    seed(app)
    response = client.put(
        "/api/v1/admin/settings",
        headers=auth,
        json={"values": {"phone": "+254 700 000000", "office_hours": "Mon-Fri 8-5"}},
    )
    assert response.status_code == 200
    values = client.get("/api/v1/settings").get_json()
    assert values["phone"] == "+254 700 000000"
    assert values["office_hours"] == "Mon-Fri 8-5"


def test_put_rejects_a_key_nothing_reads(app, client, auth):
    seed(app)
    response = client.put(
        "/api/v1/admin/settings", headers=auth, json={"values": {"invented_key": "x"}}
    )
    assert response.status_code == 400
    assert error_of(response)["fields"] == {"invented_key": "Unknown setting."}


def test_put_requires_the_values_object(client, auth):
    response = client.put("/api/v1/admin/settings", headers=auth, json={})
    assert response.status_code == 400
    assert "values" in error_of(response)["fields"]


def test_put_rejects_unknown_top_level_fields(client, auth):
    response = client.put(
        "/api/v1/admin/settings", headers=auth, json={"values": {}, "force": True}
    )
    assert response.status_code == 400
    assert "force" in error_of(response)["fields"]


def test_placeholders_are_empty_rather_than_invented(app, client):
    """SPEC section 2 forbids faking these; they ship blank for the school to fill."""
    seed(app)
    values = client.get("/api/v1/settings").get_json()
    for key in (
        "map_embed_url",
        "office_hours",
        "youtube_url",
        "hero_image_url",
        "application_form_url",
        "fee_structure_url",
        "academic_calendar_url",
        "virtual_tour_url",
    ):
        assert values[key] == "", key
