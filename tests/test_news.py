"""News: admin CRUD, publishing, slug uniqueness, and the public boundary."""

from __future__ import annotations

from .conftest import error_of


def create_article(client, auth, **overrides):
    payload = {"title": "Prize giving day", "body": "Body copy.", "category": "Events"}
    payload.update(overrides)
    return client.post("/api/v1/admin/news", headers=auth, json=payload)


def test_create_returns_201_and_derives_a_slug(client, auth):
    response = create_article(client, auth)
    assert response.status_code == 201
    article = response.get_json()
    assert article["slug"] == "prize-giving-day"
    assert article["is_published"] is False
    assert article["published_at"] is None


def test_slug_is_made_unique_across_identical_titles(client, auth):
    slugs = [create_article(client, auth).get_json()["slug"] for _ in range(3)]
    assert slugs == ["prize-giving-day", "prize-giving-day-2", "prize-giving-day-3"]
    assert len(set(slugs)) == 3


def test_an_explicit_slug_is_honoured_and_still_deduplicated(client, auth):
    first = create_article(client, auth, slug="open-day").get_json()
    second = create_article(client, auth, slug="open-day").get_json()
    assert first["slug"] == "open-day"
    assert second["slug"] == "open-day-2"


def test_slug_must_be_a_slug(client, auth):
    response = create_article(client, auth, slug="Not A Slug!")
    assert response.status_code == 400
    assert "slug" in error_of(response)["fields"]


def test_title_is_required(client, auth):
    response = client.post("/api/v1/admin/news", headers=auth, json={"body": "x"})
    assert response.status_code == 400
    assert error_of(response)["fields"]["title"] == "This field is required."


def test_unknown_fields_are_rejected(client, auth):
    response = create_article(client, auth, sneaky="value")
    assert response.status_code == 400
    assert error_of(response)["fields"] == {"sneaky": "Unknown field."}


def test_excerpt_length_is_capped(client, auth):
    response = create_article(client, auth, excerpt="x" * 301)
    assert response.status_code == 400
    assert "excerpt" in error_of(response)["fields"]


def test_update_only_touches_the_fields_that_were_sent(client, auth):
    article = create_article(client, auth, excerpt="Original excerpt.").get_json()
    response = client.put(
        f"/api/v1/admin/news/{article['id']}", headers=auth, json={"title": "Renamed"}
    )
    assert response.status_code == 200
    updated = response.get_json()
    assert updated["title"] == "Renamed"
    assert updated["excerpt"] == "Original excerpt."
    assert updated["slug"] == article["slug"]


def test_update_can_clear_a_nullable_field_with_an_explicit_null(client, auth):
    article = create_article(client, auth, excerpt="Original.").get_json()
    response = client.put(
        f"/api/v1/admin/news/{article['id']}", headers=auth, json={"excerpt": None}
    )
    assert response.status_code == 200
    assert response.get_json()["excerpt"] is None


def test_publish_sets_published_at_once(client, auth):
    article = create_article(client, auth).get_json()
    published = client.patch(
        f"/api/v1/admin/news/{article['id']}/publish", headers=auth, json={"is_published": True}
    ).get_json()
    assert published["is_published"] is True
    assert published["published_at"] is not None


def test_publish_requires_the_flag(client, auth):
    article = create_article(client, auth).get_json()
    response = client.patch(
        f"/api/v1/admin/news/{article['id']}/publish", headers=auth, json={}
    )
    assert response.status_code == 400
    assert "is_published" in error_of(response)["fields"]


def test_the_public_list_shows_only_published_articles(client, auth):
    draft = create_article(client, auth, title="Draft piece").get_json()
    live = create_article(client, auth, title="Live piece").get_json()
    client.patch(
        f"/api/v1/admin/news/{live['id']}/publish", headers=auth, json={"is_published": True}
    )

    payload = client.get("/api/v1/news").get_json()
    slugs = [item["slug"] for item in payload["items"]]
    assert live["slug"] in slugs
    assert draft["slug"] not in slugs

    assert client.get(f"/api/v1/news/{live['slug']}").status_code == 200
    assert client.get(f"/api/v1/news/{draft['slug']}").status_code == 404


def test_the_public_list_envelope(client, auth):
    for index in range(3):
        article = create_article(client, auth, title=f"Story {index}").get_json()
        client.patch(
            f"/api/v1/admin/news/{article['id']}/publish",
            headers=auth,
            json={"is_published": True},
        )
    payload = client.get("/api/v1/news?per_page=2").get_json()
    assert set(payload) == {"items", "page", "per_page", "total", "pages"}
    assert payload == {**payload, "page": 1, "per_page": 2, "total": 3, "pages": 2}
    assert len(payload["items"]) == 2
    # The public list never leaks the draft flag or the body.
    assert "is_published" not in payload["items"][0]
    assert "body" not in payload["items"][0]


def test_the_public_detail_includes_the_body(client, auth):
    article = create_article(client, auth, body="The full story.").get_json()
    client.patch(
        f"/api/v1/admin/news/{article['id']}/publish", headers=auth, json={"is_published": True}
    )
    detail = client.get(f"/api/v1/news/{article['slug']}").get_json()
    assert detail["body"] == "The full story."


def test_public_filters_by_category_and_search(client, auth):
    for title, category in (("Athletics day", "Sports"), ("Science fair", "Academics")):
        article = create_article(client, auth, title=title, category=category).get_json()
        client.patch(
            f"/api/v1/admin/news/{article['id']}/publish",
            headers=auth,
            json={"is_published": True},
        )

    sports = client.get("/api/v1/news?category=sports").get_json()
    assert [item["title"] for item in sports["items"]] == ["Athletics day"]

    found = client.get("/api/v1/news?q=science").get_json()
    assert [item["title"] for item in found["items"]] == ["Science fair"]


def test_categories_endpoint_lists_published_categories_only(client, auth):
    create_article(client, auth, title="Hidden", category="Secret")
    live = create_article(client, auth, title="Shown", category="Sports").get_json()
    client.patch(
        f"/api/v1/admin/news/{live['id']}/publish", headers=auth, json={"is_published": True}
    )
    assert client.get("/api/v1/news/categories").get_json() == {"items": ["Sports"]}


def test_delete_removes_it_everywhere(client, auth):
    article = create_article(client, auth).get_json()
    assert client.delete(f"/api/v1/admin/news/{article['id']}", headers=auth).status_code == 204
    assert client.get(f"/api/v1/admin/news/{article['id']}", headers=auth).status_code == 404


def test_missing_article_returns_the_not_found_envelope(client, auth):
    response = client.get("/api/v1/admin/news/424242", headers=auth)
    assert response.status_code == 404
    assert error_of(response)["code"] == "NOT_FOUND"
