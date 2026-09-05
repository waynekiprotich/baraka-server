"""Shared pytest fixtures. These run against the real baraka_test database."""

from __future__ import annotations

import shutil

import pytest

from app import create_app
from app.config import TestConfig
from app.extensions import db
from app.models import AdminUser

ADMIN_EMAIL = "tester@barakaschoolkapsabet.ac.ke"
ADMIN_PASSWORD = "test-password-1234"


@pytest.fixture(scope="session")
def app():
    application = create_app(TestConfig)
    with application.app_context():
        db.drop_all()
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()
    shutil.rmtree(TestConfig.UPLOAD_DIR, ignore_errors=True)


@pytest.fixture(autouse=True)
def clean_tables(app):
    """Every test starts from an empty database."""
    db.session.remove()
    for table in reversed(db.metadata.sorted_tables):
        db.session.execute(table.delete())
    db.session.commit()
    yield
    db.session.remove()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def admin(app):
    user = AdminUser(email=ADMIN_EMAIL, name="Test Administrator")
    user.set_password(ADMIN_PASSWORD)
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def tokens(client, admin):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200, response.get_json()
    return response.get_json()


@pytest.fixture
def auth(tokens):
    """Authorization header for an access token."""
    return {"Authorization": f"Bearer {tokens['access_token']}"}


@pytest.fixture
def refresh_auth(tokens):
    return {"Authorization": f"Bearer {tokens['refresh_token']}"}


def error_of(response) -> dict:
    """The error object from a response, asserting the envelope's shape."""
    payload = response.get_json()
    assert isinstance(payload, dict), payload
    assert set(payload) == {"error"}, payload
    error = payload["error"]
    assert isinstance(error["code"], str) and error["code"]
    assert isinstance(error["message"], str) and error["message"]
    return error
