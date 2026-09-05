"""The authentication flow: login, refresh, me, logout, change-password."""

from __future__ import annotations

from app.extensions import db
from app.models import AdminUser

from .conftest import ADMIN_EMAIL, ADMIN_PASSWORD, error_of


def test_login_returns_tokens_and_a_user_without_a_hash(client, admin):
    response = client.post(
        "/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert set(payload) == {"access_token", "refresh_token", "user"}
    assert payload["user"]["email"] == ADMIN_EMAIL
    assert "password_hash" not in payload["user"]
    assert "password" not in payload["user"]


def test_login_is_case_insensitive_on_email(client, admin):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": ADMIN_EMAIL.upper(), "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200


def test_wrong_password_and_unknown_email_are_indistinguishable(client, admin):
    wrong = client.post(
        "/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": "not-the-password"}
    )
    unknown = client.post(
        "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "not-the-password"}
    )
    assert wrong.status_code == unknown.status_code == 401
    assert error_of(wrong) == error_of(unknown)
    assert error_of(wrong)["code"] == "INVALID_CREDENTIALS"


def test_login_validates_its_body(client):
    response = client.post("/api/v1/auth/login", json={"email": "nope"})
    assert response.status_code == 400
    error = error_of(response)
    assert error["code"] == "VALIDATION_ERROR"
    assert set(error["fields"]) == {"email", "password"}


def test_login_rejects_unknown_fields(client, admin):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD, "remember": True},
    )
    assert response.status_code == 400
    assert error_of(response)["fields"] == {"remember": "Unknown field."}


def test_login_updates_last_login_at(client, admin):
    assert admin.last_login_at is None
    client.post("/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    db.session.refresh(admin)
    assert admin.last_login_at is not None


def test_login_is_rate_limited_after_five_attempts(client, admin):
    codes = []
    for _ in range(7):
        response = client.post(
            "/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong-one"}
        )
        codes.append(response.status_code)
    assert codes[:5] == [401] * 5
    assert codes[5:] == [429, 429]


def test_rate_limit_counts_survive_the_rejected_request(client, admin):
    """The counter is written on its own connection, so a 401 still counts."""
    from app.models import RateLimitHit

    for _ in range(3):
        client.post("/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong"})
    assert db.session.query(RateLimitHit).count() == 3


def test_me_returns_the_signed_in_user(client, auth, admin):
    response = client.get("/api/v1/auth/me", headers=auth)
    assert response.status_code == 200
    assert response.get_json()["user"]["email"] == ADMIN_EMAIL


def test_me_without_a_token(client):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert error_of(response)["code"] == "INVALID_TOKEN"


def test_me_with_a_garbage_token(client):
    response = client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer not.a.real.token"}
    )
    assert response.status_code == 401
    assert error_of(response)["code"] == "INVALID_TOKEN"


def test_refresh_issues_a_new_access_token(client, refresh_auth):
    response = client.post("/api/v1/auth/refresh", headers=refresh_auth)
    assert response.status_code == 200
    assert "access_token" in response.get_json()


def test_refresh_refuses_an_access_token(client, auth):
    response = client.post("/api/v1/auth/refresh", headers=auth)
    assert response.status_code == 401


def test_admin_route_refuses_a_refresh_token(client, refresh_auth):
    response = client.get("/api/v1/admin/stats", headers=refresh_auth)
    assert response.status_code == 401
    assert error_of(response)["code"] == "INVALID_TOKEN"


def test_logout_actually_revokes_the_token(client, auth):
    assert client.get("/api/v1/auth/me", headers=auth).status_code == 200
    assert client.post("/api/v1/auth/logout", headers=auth).status_code == 204

    response = client.get("/api/v1/auth/me", headers=auth)
    assert response.status_code == 401
    assert error_of(response)["code"] == "TOKEN_REVOKED"


def test_logout_refresh_revokes_the_refresh_token(client, refresh_auth):
    assert client.post("/api/v1/auth/logout-refresh", headers=refresh_auth).status_code == 204
    response = client.post("/api/v1/auth/refresh", headers=refresh_auth)
    assert response.status_code == 401
    assert error_of(response)["code"] == "TOKEN_REVOKED"


def test_change_password_requires_the_current_one(client, auth):
    response = client.post(
        "/api/v1/auth/change-password",
        headers=auth,
        json={"current_password": "wrong", "new_password": "a-long-enough-one"},
    )
    assert response.status_code == 400
    assert "current_password" in error_of(response)["fields"]


def test_change_password_enforces_a_minimum_length(client, auth):
    response = client.post(
        "/api/v1/auth/change-password",
        headers=auth,
        json={"current_password": ADMIN_PASSWORD, "new_password": "short"},
    )
    assert response.status_code == 400
    assert error_of(response)["fields"]["new_password"].startswith("Must be at least 10")


def test_change_password_rejects_reusing_the_same_password(client, auth):
    response = client.post(
        "/api/v1/auth/change-password",
        headers=auth,
        json={"current_password": ADMIN_PASSWORD, "new_password": ADMIN_PASSWORD},
    )
    assert response.status_code == 400
    assert "new_password" in error_of(response)["fields"]


def test_change_password_works_and_the_old_one_stops_working(client, auth, admin):
    response = client.post(
        "/api/v1/auth/change-password",
        headers=auth,
        json={"current_password": ADMIN_PASSWORD, "new_password": "a-brand-new-password"},
    )
    assert response.status_code == 200

    old = client.post(
        "/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    assert old.status_code == 401
    new = client.post(
        "/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": "a-brand-new-password"}
    )
    assert new.status_code == 200


def test_password_hash_is_scrypt_and_never_the_plaintext(admin):
    stored = db.session.get(AdminUser, admin.id)
    assert stored.password_hash.startswith("scrypt:")
    assert ADMIN_PASSWORD not in stored.password_hash
