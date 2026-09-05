"""Events: admin CRUD, the time constraint, and upcoming/past filtering."""

from __future__ import annotations

from datetime import timedelta

from app.models import utcnow

from .conftest import error_of


def iso(value):
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def create_event(client, auth, **overrides):
    payload = {
        "title": "Music festival",
        "summary": "The annual festival.",
        "description": "Full details.",
        "starts_at": iso(utcnow() + timedelta(days=30)),
        "location": "School hall",
    }
    payload.update(overrides)
    return client.post("/api/v1/admin/events", headers=auth, json=payload)


def test_create_derives_a_slug_and_starts_unpublished(client, auth):
    response = create_event(client, auth)
    assert response.status_code == 201
    event = response.get_json()
    assert event["slug"] == "music-festival"
    assert event["is_published"] is False


def test_slug_uniqueness(client, auth):
    slugs = [create_event(client, auth).get_json()["slug"] for _ in range(2)]
    assert slugs == ["music-festival", "music-festival-2"]


def test_starts_at_is_required(client, auth):
    response = client.post("/api/v1/admin/events", headers=auth, json={"title": "No date"})
    assert response.status_code == 400
    assert "starts_at" in error_of(response)["fields"]


def test_starts_at_must_be_iso_8601(client, auth):
    response = create_event(client, auth, starts_at="next tuesday")
    assert response.status_code == 400
    assert "starts_at" in error_of(response)["fields"]


def test_ends_at_cannot_precede_starts_at(client, auth):
    start = utcnow() + timedelta(days=5)
    response = create_event(
        client, auth, starts_at=iso(start), ends_at=iso(start - timedelta(hours=2))
    )
    assert response.status_code == 400
    assert "ends_at" in error_of(response)["fields"]


def test_update_and_publish(client, auth):
    event = create_event(client, auth).get_json()
    updated = client.put(
        f"/api/v1/admin/events/{event['id']}", headers=auth, json={"location": "School field"}
    ).get_json()
    assert updated["location"] == "School field"
    assert updated["title"] == "Music festival"

    published = client.patch(
        f"/api/v1/admin/events/{event['id']}/publish", headers=auth, json={"is_published": True}
    ).get_json()
    assert published["is_published"] is True


def test_public_sees_only_published_events(client, auth):
    draft = create_event(client, auth, title="Staff meeting").get_json()
    live = create_event(client, auth, title="Open day").get_json()
    client.patch(
        f"/api/v1/admin/events/{live['id']}/publish", headers=auth, json={"is_published": True}
    )

    slugs = [item["slug"] for item in client.get("/api/v1/events").get_json()["items"]]
    assert slugs == [live["slug"]]
    assert client.get(f"/api/v1/events/{draft['slug']}").status_code == 404


def test_upcoming_filter(client, auth):
    past = create_event(
        client, auth, title="Last term concert", starts_at=iso(utcnow() - timedelta(days=10))
    ).get_json()
    future = create_event(
        client, auth, title="Next term concert", starts_at=iso(utcnow() + timedelta(days=10))
    ).get_json()
    for event in (past, future):
        client.patch(
            f"/api/v1/admin/events/{event['id']}/publish",
            headers=auth,
            json={"is_published": True},
        )

    upcoming = client.get("/api/v1/events?upcoming=true").get_json()
    assert [item["slug"] for item in upcoming["items"]] == [future["slug"]]

    previous = client.get("/api/v1/events?upcoming=false").get_json()
    assert [item["slug"] for item in previous["items"]] == [past["slug"]]

    assert client.get("/api/v1/events").get_json()["total"] == 2


def test_upcoming_must_be_a_boolean(client):
    response = client.get("/api/v1/events?upcoming=maybe")
    assert response.status_code == 400
    assert error_of(response)["fields"]["upcoming"] == "Must be true or false."


def test_list_omits_the_description_and_detail_includes_it(client, auth):
    event = create_event(client, auth, description="Every detail.").get_json()
    client.patch(
        f"/api/v1/admin/events/{event['id']}/publish", headers=auth, json={"is_published": True}
    )
    listed = client.get("/api/v1/events").get_json()["items"][0]
    assert "description" not in listed
    detail = client.get(f"/api/v1/events/{event['slug']}").get_json()
    assert detail["description"] == "Every detail."


def test_delete(client, auth):
    event = create_event(client, auth).get_json()
    assert client.delete(f"/api/v1/admin/events/{event['id']}", headers=auth).status_code == 204
    assert client.get(f"/api/v1/admin/events/{event['id']}", headers=auth).status_code == 404
