"""Gallery categories, images, ordering and the SET NULL delete behaviour."""

from __future__ import annotations

from .conftest import error_of


def make_category(client, auth, name="Sports"):
    return client.post(
        "/api/v1/admin/gallery/categories", headers=auth, json={"name": name}
    ).get_json()


def make_image(client, auth, category_id=None, **overrides):
    payload = {
        "alt_text": "Learners on the athletics track at Kapsabet",
        "url": "/uploads/example.png",
        "category_id": category_id,
    }
    payload.update(overrides)
    return client.post("/api/v1/admin/gallery/images", headers=auth, json=payload)


def test_category_create_derives_a_slug(client, auth):
    category = make_category(client, auth, "School Events")
    assert category["slug"] == "school-events"
    assert category["image_count"] == 0


def test_category_slug_uniqueness(client, auth):
    slugs = [make_category(client, auth, "Sports")["slug"] for _ in range(2)]
    assert slugs == ["sports", "sports-2"]


def test_category_name_is_required(client, auth):
    response = client.post("/api/v1/admin/gallery/categories", headers=auth, json={})
    assert response.status_code == 400
    assert "name" in error_of(response)["fields"]


def test_category_update(client, auth):
    category = make_category(client, auth)
    response = client.put(
        f"/api/v1/admin/gallery/categories/{category['id']}",
        headers=auth,
        json={"name": "Athletics", "position": 4},
    )
    assert response.status_code == 200
    assert response.get_json()["name"] == "Athletics"
    assert response.get_json()["position"] == 4


def test_alt_text_is_required_on_every_image(client, auth):
    response = client.post(
        "/api/v1/admin/gallery/images", headers=auth, json={"url": "/uploads/x.png"}
    )
    assert response.status_code == 400
    assert error_of(response)["fields"]["alt_text"] == "This field is required."


def test_url_is_required_on_every_image(client, auth):
    response = client.post(
        "/api/v1/admin/gallery/images", headers=auth, json={"alt_text": "Something"}
    )
    assert response.status_code == 400
    assert "url" in error_of(response)["fields"]


def test_image_create_and_public_listing(client, auth):
    category = make_category(client, auth)
    created = make_image(client, auth, category["id"])
    assert created.status_code == 201
    image = created.get_json()
    assert image["category"]["slug"] == "sports"

    listing = client.get("/api/v1/gallery").get_json()
    assert listing["total"] == 1
    assert listing["items"][0]["alt_text"] == image["alt_text"]
    # The public shape never exposes the disk key.
    assert "storage_key" not in listing["items"][0]


def test_public_gallery_filters_by_category_slug(client, auth):
    sports = make_category(client, auth, "Sports")
    campus = make_category(client, auth, "Campus")
    make_image(client, auth, sports["id"], alt_text="A football fixture in progress")
    make_image(client, auth, campus["id"], alt_text="The science and ICT block")

    filtered = client.get("/api/v1/gallery?category=sports").get_json()
    assert filtered["total"] == 1
    assert filtered["items"][0]["alt_text"] == "A football fixture in progress"


def test_public_gallery_with_an_unknown_category_is_a_404(client):
    response = client.get("/api/v1/gallery?category=nope")
    assert response.status_code == 404
    assert error_of(response)["code"] == "NOT_FOUND"


def test_category_listing_carries_image_counts(client, auth):
    category = make_category(client, auth)
    make_image(client, auth, category["id"])
    make_image(client, auth, category["id"], alt_text="A second athletics photograph")
    items = client.get("/api/v1/gallery/categories").get_json()["items"]
    assert items[0]["image_count"] == 2


def test_an_image_cannot_point_at_a_category_that_does_not_exist(client, auth):
    response = make_image(client, auth, 9999)
    assert response.status_code == 404


def test_deleting_a_category_keeps_its_images(client, auth):
    category = make_category(client, auth)
    image = make_image(client, auth, category["id"]).get_json()

    assert (
        client.delete(
            f"/api/v1/admin/gallery/categories/{category['id']}", headers=auth
        ).status_code
        == 204
    )
    survivor = client.get(f"/api/v1/admin/gallery/images/{image['id']}", headers=auth)
    assert survivor.status_code == 200
    assert survivor.get_json()["category"] is None


def test_reorder_writes_positions_one_to_n(client, auth):
    ids = [
        make_image(client, auth, alt_text=f"Placeholder photograph {index}").get_json()["id"]
        for index in range(3)
    ]
    reversed_ids = list(reversed(ids))
    response = client.post(
        "/api/v1/admin/gallery/images/reorder", headers=auth, json={"ids": reversed_ids}
    )
    assert response.status_code == 200
    items = response.get_json()["items"]
    assert [item["id"] for item in items] == reversed_ids
    assert [item["position"] for item in items] == [1, 2, 3]

    public_order = [item["id"] for item in client.get("/api/v1/gallery").get_json()["items"]]
    assert public_order == reversed_ids


def test_reorder_rejects_unknown_ids(client, auth):
    response = client.post(
        "/api/v1/admin/gallery/images/reorder", headers=auth, json={"ids": [1234]}
    )
    assert response.status_code == 400
    assert "ids" in error_of(response)["fields"]


def test_reorder_rejects_duplicates_and_empty_lists(client, auth):
    image = make_image(client, auth).get_json()
    duplicated = client.post(
        "/api/v1/admin/gallery/images/reorder",
        headers=auth,
        json={"ids": [image["id"], image["id"]]},
    )
    assert duplicated.status_code == 400
    empty = client.post(
        "/api/v1/admin/gallery/images/reorder", headers=auth, json={"ids": []}
    )
    assert empty.status_code == 400


def test_image_update_and_delete(client, auth):
    image = make_image(client, auth).get_json()
    updated = client.put(
        f"/api/v1/admin/gallery/images/{image['id']}", headers=auth, json={"is_featured": True}
    )
    assert updated.get_json()["is_featured"] is True

    assert (
        client.delete(f"/api/v1/admin/gallery/images/{image['id']}", headers=auth).status_code
        == 204
    )
    assert client.get("/api/v1/gallery").get_json()["total"] == 0
