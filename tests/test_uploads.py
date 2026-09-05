"""Upload validation: the bytes are decoded, never the extension trusted."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from PIL import Image

from .conftest import error_of


def png_bytes(width=1200, height=800, colour=(60, 30, 114)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), colour).save(buffer, format="PNG")
    return buffer.getvalue()


def jpeg_with_exif() -> bytes:
    image = Image.new("RGB", (900, 450), (200, 120, 60))
    exif = image.getexif()
    exif[271] = "SecretCameraMake"
    exif[272] = "SecretModel"
    exif[274] = 6  # orientation: rotate 90 degrees
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", exif=exif)
    return buffer.getvalue()


def upload(client, auth, data: bytes, filename: str, content_type: str = "image/png"):
    return client.post(
        "/api/v1/admin/uploads",
        headers=auth,
        data={"file": (io.BytesIO(data), filename, content_type)},
        content_type="multipart/form-data",
    )


def test_a_real_png_is_accepted(client, auth, app):
    response = upload(client, auth, png_bytes(), "photo.png")
    assert response.status_code == 201
    payload = response.get_json()
    assert set(payload) == {"url", "thumb_url", "width", "height", "storage_key"}
    assert payload["width"] == 1200
    assert payload["height"] == 800

    directory = Path(app.config["UPLOAD_DIR"])
    assert (directory / payload["storage_key"]).is_file()
    assert (directory / Path(payload["thumb_url"]).name).is_file()


def test_the_client_filename_is_discarded_for_a_uuid(client, auth):
    payload = upload(client, auth, png_bytes(), "../../etc/passwd.png").get_json()
    assert "passwd" not in payload["storage_key"]
    stem = Path(payload["storage_key"]).stem
    assert len(stem) == 32 and all(character in "0123456789abcdef" for character in stem)


def test_the_long_edge_is_capped_at_2000px(client, auth):
    payload = upload(client, auth, png_bytes(3000, 1500), "big.png").get_json()
    assert payload["width"] == 2000
    assert payload["height"] == 1000


def test_a_thumbnail_is_written_at_480px(client, auth, app):
    payload = upload(client, auth, png_bytes(1600, 800), "photo.png").get_json()
    thumb = Path(app.config["UPLOAD_DIR"]) / Path(payload["thumb_url"]).name
    with Image.open(thumb) as image:
        assert max(image.size) == 480


def test_exif_is_stripped_and_orientation_applied(client, auth, app):
    payload = upload(client, auth, jpeg_with_exif(), "camera.jpg", "image/jpeg").get_json()
    stored = Path(app.config["UPLOAD_DIR"]) / payload["storage_key"]
    with Image.open(stored) as image:
        assert dict(image.getexif()) == {}
        # Orientation 6 means the 900x450 source is stored rotated.
        assert image.size == (450, 900)


def test_a_text_file_renamed_png_is_refused(client, auth):
    response = upload(client, auth, b"this is not an image at all" * 40, "fake.png")
    assert response.status_code == 415
    assert error_of(response)["code"] == "UNSUPPORTED_MEDIA_TYPE"


def test_a_gif_is_refused_even_though_pillow_reads_it(client, auth):
    buffer = io.BytesIO()
    Image.new("P", (40, 40)).save(buffer, format="GIF")
    response = upload(client, auth, buffer.getvalue(), "animation.gif", "image/gif")
    assert response.status_code == 415


def test_an_empty_file_is_refused(client, auth):
    response = upload(client, auth, b"", "empty.png")
    assert response.status_code in (400, 415)


def test_no_file_at_all_is_a_validation_error(client, auth):
    response = client.post(
        "/api/v1/admin/uploads", headers=auth, data={}, content_type="multipart/form-data"
    )
    assert response.status_code == 400
    assert error_of(response)["fields"]["file"] == "Choose an image to upload."


def test_a_file_over_the_cap_is_refused(client, auth, app):
    oversized = b"\x89PNG\r\n\x1a\n" + b"\x00" * (app.config["MAX_UPLOAD_BYTES"] + 1)
    response = upload(client, auth, oversized, "huge.png")
    assert response.status_code == 413
    assert error_of(response)["code"] == "PAYLOAD_TOO_LARGE"


@pytest.mark.parametrize("fmt", ["PNG", "JPEG", "WEBP"])
def test_every_allowed_format_round_trips(client, auth, fmt):
    buffer = io.BytesIO()
    Image.new("RGB", (600, 400), (10, 20, 30)).save(buffer, format=fmt)
    response = upload(client, auth, buffer.getvalue(), f"image.{fmt.lower()}")
    assert response.status_code == 201, response.get_json()


def test_uploads_are_served_with_immutable_caching(client, auth):
    payload = upload(client, auth, png_bytes(), "photo.png").get_json()
    response = client.get(payload["url"])
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "public, max-age=31536000, immutable"
    assert response.headers["Content-Type"] == "image/png"


def test_a_missing_upload_returns_the_not_found_envelope(client):
    response = client.get("/uploads/0123456789abcdef0123456789abcdef.png")
    assert response.status_code == 404
    assert error_of(response)["code"] == "NOT_FOUND"


def test_the_upload_route_refuses_a_non_image_extension(client):
    response = client.get("/uploads/secrets.env")
    assert response.status_code == 415
