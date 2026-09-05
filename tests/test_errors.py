"""The error envelope, the cache boundary, compression and headers."""

from __future__ import annotations

import gzip

import pytest

from app.errors import ApiError

from .conftest import error_of


def test_the_envelope_shape_on_a_404(client):
    response = client.get("/api/v1/news/nothing-here")
    assert response.status_code == 404
    assert response.get_json() == {
        "error": {"code": "NOT_FOUND", "message": "That article does not exist."}
    }


def test_the_envelope_shape_on_a_validation_error(client):
    response = client.post("/api/v1/enquiries", json={})
    assert response.status_code == 400
    payload = response.get_json()
    assert set(payload["error"]) == {"code", "message", "fields"}
    assert payload["error"]["code"] == "VALIDATION_ERROR"
    assert all(isinstance(value, str) for value in payload["error"]["fields"].values())


def test_an_unknown_route_still_uses_the_envelope(client):
    response = client.get("/api/v1/there-is-no-such-thing")
    assert response.status_code == 404
    assert error_of(response)["code"] == "NOT_FOUND"


def test_a_wrong_method_still_uses_the_envelope(client):
    response = client.delete("/api/v1/settings")
    assert response.status_code == 405
    assert error_of(response)["code"] == "NOT_FOUND"


def test_a_malformed_json_body_is_a_validation_error(client):
    response = client.post(
        "/api/v1/enquiries", data="{not json", content_type="application/json"
    )
    assert response.status_code == 400
    assert error_of(response)["code"] == "VALIDATION_ERROR"


def test_a_500_returns_a_reference_and_nothing_that_describes_the_failure(caplog):
    # A separate app: a route can only be registered before the first request.
    from app import create_app
    from app.config import TestConfig

    application = create_app(TestConfig)

    @application.route("/api/v1/__boom")
    def boom():  # pragma: no cover - invoked through the test client
        raise RuntimeError("a secret internal detail nobody outside should read")

    with caplog.at_level("CRITICAL"):
        response = application.test_client().get("/api/v1/__boom")
    assert response.status_code == 500
    error = response.get_json()["error"]
    assert set(error) == {"code", "message", "reference"}
    assert error["code"] == "INTERNAL_ERROR"
    assert len(error["reference"]) == 16

    body = response.get_data(as_text=True)
    assert "RuntimeError" not in body
    assert "secret internal detail" not in body
    assert "Traceback" not in body


def test_an_api_error_carries_its_own_status_and_code():
    error = ApiError("Nope.", code="CONFLICT", status=409, fields={"slug": "Taken."})
    assert error.to_payload() == {
        "error": {"code": "CONFLICT", "message": "Nope.", "fields": {"slug": "Taken."}}
    }


@pytest.mark.parametrize(
    "path",
    ["/api/v1/settings", "/api/v1/news", "/api/v1/events", "/api/v1/gallery"],
)
def test_public_catalog_reads_are_cacheable_and_carry_an_etag(client, path):
    response = client.get(path)
    assert response.headers["Cache-Control"] == "public, max-age=60, stale-while-revalidate=300"
    assert response.headers["ETag"].startswith('W/"')


@pytest.mark.parametrize(
    "path",
    ["/api/v1/admin/stats", "/api/v1/admin/news", "/api/v1/admin/settings", "/api/v1/auth/me"],
)
def test_admin_and_auth_are_never_stored(client, auth, path):
    response = client.get(path, headers=auth)
    assert response.headers["Cache-Control"] == "no-store"
    assert "ETag" not in response.headers


def test_a_matching_etag_revalidates_to_304(client):
    first = client.get("/api/v1/news")
    etag = first.headers["ETag"]
    second = client.get("/api/v1/news", headers={"If-None-Match": etag})
    assert second.status_code == 304
    assert second.get_data() == b""


def test_responses_over_a_kilobyte_are_gzipped(client, auth, app):
    from app.services import settings_service

    settings_service.ensure_defaults()

    plain = client.get("/api/v1/admin/settings", headers=auth)
    assert "Content-Encoding" not in plain.headers
    assert len(plain.get_data()) > app.config["GZIP_MIN_BYTES"]

    compressed = client.get(
        "/api/v1/admin/settings", headers={**auth, "Accept-Encoding": "gzip"}
    )
    assert compressed.headers["Content-Encoding"] == "gzip"
    assert len(compressed.get_data()) < len(plain.get_data())
    assert gzip.decompress(compressed.get_data()) == plain.get_data()


def test_small_responses_are_left_alone(client):
    response = client.get("/api/v1/health", headers={"Accept-Encoding": "gzip"})
    assert "Content-Encoding" not in response.headers


def test_security_headers_are_set_on_every_response(client):
    for path in ("/api/v1/health", "/api/v1/news/nothing"):
        response = client.get(path)
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
        assert "Content-Security-Policy" in response.headers
        assert "Permissions-Policy" in response.headers
        assert response.headers["X-Request-Id"]


def test_an_inbound_request_id_is_reused(client):
    response = client.get("/api/v1/health", headers={"X-Request-Id": "abc123"})
    assert response.headers["X-Request-Id"] == "abc123"


def test_health_reports_the_database(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok", "database": True}


def test_pagination_arguments_are_validated(client):
    response = client.get("/api/v1/news?page=banana")
    assert response.status_code == 400
    assert "page" in error_of(response)["fields"]


def test_per_page_is_clamped_rather_than_rejected(client):
    payload = client.get("/api/v1/news?per_page=9999").get_json()
    assert payload["per_page"] == 100
