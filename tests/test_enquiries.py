"""Enquiries: the public write path and the admin inbox."""

from __future__ import annotations

from app.extensions import db
from app.models import Enquiry

from .conftest import error_of

VALID = {
    "name": "Jane Kiptoo",
    "email": "jane@example.com",
    "phone": "+254712345678",
    "subject": "Grade 4 place",
    "message": "Is a Grade 4 place available for the 2027 intake?",
    "learner_name": "Alex Kiptoo",
    "grade_applying": "Grade 4",
    "source": "admissions",
}


def test_a_valid_enquiry_is_stored(client):
    response = client.post("/api/v1/enquiries", json=VALID)
    assert response.status_code == 201
    assert response.get_json()["ok"] is True

    stored = db.session.query(Enquiry).one()
    assert stored.name == "Jane Kiptoo"
    assert stored.email == "jane@example.com"
    assert stored.source == "admissions"
    assert stored.status == "new"


def test_the_ip_is_hashed_never_stored_raw(client):
    client.post("/api/v1/enquiries", json=VALID)
    stored = db.session.query(Enquiry).one()
    assert stored.ip_hash is not None
    assert len(stored.ip_hash) == 64
    assert "127.0.0.1" not in stored.ip_hash


def test_source_defaults_to_contact(client):
    payload = {key: value for key, value in VALID.items() if key != "source"}
    client.post("/api/v1/enquiries", json=payload)
    assert db.session.query(Enquiry).one().source == "contact"


def test_source_is_constrained(client):
    response = client.post("/api/v1/enquiries", json={**VALID, "source": "walk-in"})
    assert response.status_code == 400
    assert "source" in error_of(response)["fields"]


def test_required_fields(client):
    response = client.post("/api/v1/enquiries", json={})
    assert response.status_code == 400
    fields = error_of(response)["fields"]
    assert set(fields) == {"name", "email", "message"}


def test_email_must_look_like_an_email(client):
    response = client.post("/api/v1/enquiries", json={**VALID, "email": "not-an-email"})
    assert response.status_code == 400
    assert "email" in error_of(response)["fields"]


def test_message_length_is_capped(client):
    response = client.post("/api/v1/enquiries", json={**VALID, "message": "x" * 5001})
    assert response.status_code == 400
    assert "message" in error_of(response)["fields"]


def test_the_honeypot_swallows_the_submission_without_saying_so(client):
    response = client.post("/api/v1/enquiries", json={**VALID, "website": "http://spam.example"})
    assert response.status_code == 201
    assert db.session.query(Enquiry).count() == 0


def test_the_message_is_stored_verbatim_as_plain_text(client):
    hostile = "<script>alert('x')</script> & \"quotes\""
    client.post("/api/v1/enquiries", json={**VALID, "message": hostile})
    assert db.session.query(Enquiry).one().message == hostile


def test_enquiries_are_rate_limited(client):
    codes = [client.post("/api/v1/enquiries", json=VALID).status_code for _ in range(7)]
    assert codes[:5] == [201] * 5
    assert codes[5:] == [429, 429]
    assert error_of(client.post("/api/v1/enquiries", json=VALID))["code"] == "RATE_LIMITED"


def test_the_admin_inbox_lists_them_with_counts(client, auth):
    client.post("/api/v1/enquiries", json=VALID)
    payload = client.get("/api/v1/admin/enquiries", headers=auth).get_json()
    assert payload["total"] == 1
    assert payload["counts"]["new"] == 1
    assert payload["items"][0]["email"] == "jane@example.com"


def test_the_inbox_filters_by_status(client, auth):
    client.post("/api/v1/enquiries", json=VALID)
    enquiry_id = client.get("/api/v1/admin/enquiries", headers=auth).get_json()["items"][0]["id"]

    updated = client.patch(
        f"/api/v1/admin/enquiries/{enquiry_id}", headers=auth, json={"status": "read"}
    )
    assert updated.get_json()["status"] == "read"

    assert client.get("/api/v1/admin/enquiries?status=new", headers=auth).get_json()["total"] == 0
    assert client.get("/api/v1/admin/enquiries?status=read", headers=auth).get_json()["total"] == 1


def test_an_invalid_status_is_rejected_on_write_and_on_filter(client, auth):
    client.post("/api/v1/enquiries", json=VALID)
    enquiry_id = client.get("/api/v1/admin/enquiries", headers=auth).get_json()["items"][0]["id"]

    write = client.patch(
        f"/api/v1/admin/enquiries/{enquiry_id}", headers=auth, json={"status": "burned"}
    )
    assert write.status_code == 400
    assert "status" in error_of(write)["fields"]

    read = client.get("/api/v1/admin/enquiries?status=burned", headers=auth)
    assert read.status_code == 400


def test_delete_an_enquiry(client, auth):
    client.post("/api/v1/enquiries", json=VALID)
    enquiry_id = client.get("/api/v1/admin/enquiries", headers=auth).get_json()["items"][0]["id"]
    assert (
        client.delete(f"/api/v1/admin/enquiries/{enquiry_id}", headers=auth).status_code == 204
    )
    assert db.session.query(Enquiry).count() == 0


def test_stats_counts_enquiries(client, auth):
    client.post("/api/v1/enquiries", json=VALID)
    stats = client.get("/api/v1/admin/stats", headers=auth).get_json()
    assert stats["enquiries"]["total"] == 1
    assert stats["enquiries"]["new"] == 1
    assert stats["recent_enquiries"][0]["email"] == "jane@example.com"
