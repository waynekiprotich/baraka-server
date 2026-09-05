"""Admin authorization: @admin_required() must load the account, every time."""

from __future__ import annotations

import pytest

from app.extensions import db

from .conftest import ADMIN_EMAIL, ADMIN_PASSWORD, error_of

# Every admin path, and one method that reaches it.
ADMIN_ENDPOINTS = [
    ("get", "/api/v1/admin/stats"),
    ("get", "/api/v1/admin/news"),
    ("post", "/api/v1/admin/news"),
    ("get", "/api/v1/admin/news/1"),
    ("put", "/api/v1/admin/news/1"),
    ("patch", "/api/v1/admin/news/1/publish"),
    ("delete", "/api/v1/admin/news/1"),
    ("get", "/api/v1/admin/events"),
    ("post", "/api/v1/admin/events"),
    ("get", "/api/v1/admin/events/1"),
    ("put", "/api/v1/admin/events/1"),
    ("patch", "/api/v1/admin/events/1/publish"),
    ("delete", "/api/v1/admin/events/1"),
    ("get", "/api/v1/admin/gallery/categories"),
    ("post", "/api/v1/admin/gallery/categories"),
    ("put", "/api/v1/admin/gallery/categories/1"),
    ("delete", "/api/v1/admin/gallery/categories/1"),
    ("get", "/api/v1/admin/gallery/images"),
    ("post", "/api/v1/admin/gallery/images"),
    ("get", "/api/v1/admin/gallery/images/1"),
    ("put", "/api/v1/admin/gallery/images/1"),
    ("delete", "/api/v1/admin/gallery/images/1"),
    ("post", "/api/v1/admin/gallery/images/reorder"),
    ("get", "/api/v1/admin/settings"),
    ("put", "/api/v1/admin/settings"),
    ("get", "/api/v1/admin/enquiries"),
    ("get", "/api/v1/admin/enquiries/1"),
    ("patch", "/api/v1/admin/enquiries/1"),
    ("delete", "/api/v1/admin/enquiries/1"),
    ("post", "/api/v1/admin/uploads"),
]


@pytest.mark.parametrize(("method", "path"), ADMIN_ENDPOINTS)
def test_every_admin_endpoint_rejects_an_anonymous_caller(client, method, path):
    response = getattr(client, method)(path)
    assert response.status_code == 401, f"{method.upper()} {path} was not protected"
    assert error_of(response)["code"] == "INVALID_TOKEN"


@pytest.mark.parametrize(("method", "path"), ADMIN_ENDPOINTS)
def test_every_admin_endpoint_rejects_a_deactivated_admin(client, auth, admin, method, path):
    """A bare @jwt_required() would let this through until the token lapsed."""
    admin.is_active = False
    db.session.commit()

    response = getattr(client, method)(path, headers=auth)
    assert response.status_code == 403, f"{method.upper()} {path} served a deactivated admin"
    assert error_of(response)["code"] == "FORBIDDEN"


def test_a_deactivated_admin_cannot_log_in_again(client, admin):
    admin.is_active = False
    db.session.commit()
    response = client.post(
        "/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    assert response.status_code == 401
    assert error_of(response)["code"] == "INVALID_CREDENTIALS"


def test_a_deleted_admin_stops_working_immediately(client, auth, admin):
    db.session.delete(admin)
    db.session.commit()
    response = client.get("/api/v1/admin/stats", headers=auth)
    assert response.status_code == 401
    assert error_of(response)["code"] == "INVALID_TOKEN"


def test_public_endpoints_need_no_token(client):
    for path in (
        "/api/v1/health",
        "/api/v1/settings",
        "/api/v1/news",
        "/api/v1/news/categories",
        "/api/v1/events",
        "/api/v1/gallery",
        "/api/v1/gallery/categories",
    ):
        assert client.get(path).status_code == 200, path
