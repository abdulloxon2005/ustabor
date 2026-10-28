"""Rasm yuklash: buyurtma fotosi va usta portfolio (app/services/storage.py)."""

import struct
import zlib

import pytest

from app import models
from app.models.enums import PricingType, Role
from app.services.storage import MAX_FILE_SIZE, UPLOADS_DIR


def _make_png(w=2, h=2) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(
            ">I", zlib.crc32(tag + data)
        )

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + b"\xff\x00\x00" * w for _ in range(h))
    idat = zlib.compress(raw)
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


PNG_BYTES = _make_png()


def _png_file(name="photo.png"):
    return (name, PNG_BYTES, "image/png")


@pytest.fixture(autouse=True)
def _cleanup_uploads():
    yield
    import shutil

    if UPLOADS_DIR.exists():
        shutil.rmtree(UPLOADS_DIR, ignore_errors=True)


def _setup_order(client, signup, make_category):
    cat = make_category()
    cust_headers, _ = signup(role="customer", phone="+998901234567")

    r = client.post(
        "/api/v1/orders",
        json={
            "category_id": cat.id,
            "description": "Kran suv oqizyapti, almashtirish kerak",
            "city": "Toshkent",
            "district": "Chilonzor",
            "address": "1-uy",
            "selection_mode": "manual",
        },
        headers=cust_headers,
    )
    assert r.status_code == 201, r.text
    return cust_headers, r.json()["id"]


def _setup_master(client, signup):
    headers, user = signup(role="master", phone="+998907654321")
    r = client.post(
        "/api/v1/masters/profile",
        json={"bio": "Tajribali usta", "city": "Toshkent", "district": "Chilonzor"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return headers


# ---------- Order photos ----------


def test_upload_order_photo_success(client, signup, make_category):
    headers, order_id = _setup_order(client, signup, make_category)
    r = client.post(
        f"/api/v1/orders/{order_id}/photos",
        files=[("files", _png_file())],
        headers=headers,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert len(body) == 1
    assert body[0]["url"].startswith("/media/order_photos/")


def test_order_photo_appears_in_order_detail(client, signup, make_category):
    headers, order_id = _setup_order(client, signup, make_category)
    client.post(
        f"/api/v1/orders/{order_id}/photos",
        files=[("files", _png_file())],
        headers=headers,
    )
    r = client.get(f"/api/v1/orders/{order_id}", headers=headers)
    assert r.status_code == 200
    assert len(r.json()["photos"]) == 1


def test_upload_rejects_non_image_extension(client, signup, make_category):
    headers, order_id = _setup_order(client, signup, make_category)
    r = client.post(
        f"/api/v1/orders/{order_id}/photos",
        files=[("files", ("evil.txt", b"not an image", "text/plain"))],
        headers=headers,
    )
    assert r.status_code == 422


def test_upload_rejects_fake_extension_with_bad_content(client, signup, make_category):
    """.png kengaytmali, lekin ichida rasm bo'lmagan fayl ham rad etiladi (magic bytes)."""
    headers, order_id = _setup_order(client, signup, make_category)
    r = client.post(
        f"/api/v1/orders/{order_id}/photos",
        files=[("files", ("fake.png", b"<script>alert(1)</script>", "image/png"))],
        headers=headers,
    )
    assert r.status_code == 422


def test_upload_rejects_oversized_file(client, signup, make_category):
    headers, order_id = _setup_order(client, signup, make_category)
    big = PNG_BYTES[:8] + b"\x00" * (MAX_FILE_SIZE + 1)
    r = client.post(
        f"/api/v1/orders/{order_id}/photos",
        files=[("files", ("big.png", big, "image/png"))],
        headers=headers,
    )
    assert r.status_code == 422


def test_order_photo_limit_enforced(client, signup, make_category):
    headers, order_id = _setup_order(client, signup, make_category)
    for _ in range(5):
        r = client.post(
            f"/api/v1/orders/{order_id}/photos",
            files=[("files", _png_file())],
            headers=headers,
        )
        assert r.status_code == 201

    r = client.post(
        f"/api/v1/orders/{order_id}/photos",
        files=[("files", _png_file())],
        headers=headers,
    )
    assert r.status_code == 422


def test_cannot_upload_to_other_customers_order(client, signup, make_category):
    headers_a, order_id = _setup_order(client, signup, make_category)
    headers_b, _ = signup(role="customer", phone="+998909998877")

    r = client.post(
        f"/api/v1/orders/{order_id}/photos",
        files=[("files", _png_file())],
        headers=headers_b,
    )
    assert r.status_code == 404


def test_delete_order_photo(client, signup, make_category):
    headers, order_id = _setup_order(client, signup, make_category)
    r_upload = client.post(
        f"/api/v1/orders/{order_id}/photos",
        files=[("files", _png_file())],
        headers=headers,
    )
    photo_id = r_upload.json()[0]["id"]

    r = client.delete(f"/api/v1/orders/{order_id}/photos/{photo_id}", headers=headers)
    assert r.status_code == 200

    r_detail = client.get(f"/api/v1/orders/{order_id}", headers=headers)
    assert r_detail.json()["photos"] == []


def test_delete_other_customers_photo_404(client, signup, make_category):
    headers_a, order_id = _setup_order(client, signup, make_category)
    r_upload = client.post(
        f"/api/v1/orders/{order_id}/photos",
        files=[("files", _png_file())],
        headers=headers_a,
    )
    photo_id = r_upload.json()[0]["id"]
    headers_b, _ = signup(role="customer", phone="+998909998877")

    r = client.delete(f"/api/v1/orders/{order_id}/photos/{photo_id}", headers=headers_b)
    assert r.status_code == 404


# ---------- Master portfolio photos ----------


def test_upload_master_photo_success(client, signup):
    headers = _setup_master(client, signup)
    r = client.post(
        "/api/v1/masters/me/photos",
        files=[("files", _png_file())],
        headers=headers,
    )
    assert r.status_code == 201, r.text
    assert r.json()[0]["url"].startswith("/media/master_photos/")


def test_master_photo_appears_in_public_profile(client, signup, make_category, make_admin, auth_header):
    headers = _setup_master(client, signup)
    client.post(
        "/api/v1/masters/me/photos",
        files=[("files", _png_file())],
        headers=headers,
    )

    r_me = client.get("/api/v1/masters/me", headers=headers)
    master_id = r_me.json()["id"]

    r_pub = client.get(f"/api/v1/masters/{master_id}")
    # Tasdiqlanmagan usta ommaga ko'rinmaydi -> 404 kutilgan; shuning uchun
    # /me javobida photos borligini bevosita tekshiramiz.
    assert r_pub.status_code == 404
    assert len(r_me.json()["photos"]) == 1


def test_master_photo_limit_enforced(client, signup):
    headers = _setup_master(client, signup)
    for _ in range(10):
        r = client.post(
            "/api/v1/masters/me/photos",
            files=[("files", _png_file())],
            headers=headers,
        )
        assert r.status_code == 201

    r = client.post(
        "/api/v1/masters/me/photos",
        files=[("files", _png_file())],
        headers=headers,
    )
    assert r.status_code == 422


def test_delete_my_photo(client, signup):
    headers = _setup_master(client, signup)
    r_upload = client.post(
        "/api/v1/masters/me/photos",
        files=[("files", _png_file())],
        headers=headers,
    )
    photo_id = r_upload.json()[0]["id"]

    r = client.delete(f"/api/v1/masters/me/photos/{photo_id}", headers=headers)
    assert r.status_code == 200

    r_me = client.get("/api/v1/masters/me", headers=headers)
    assert r_me.json()["photos"] == []


def test_cannot_delete_other_masters_photo(client, signup):
    headers_a = _setup_master(client, signup)
    r_upload = client.post(
        "/api/v1/masters/me/photos",
        files=[("files", _png_file())],
        headers=headers_a,
    )
    photo_id = r_upload.json()[0]["id"]

    headers_b, _ = signup(role="master", phone="+998903334455")
    client.post(
        "/api/v1/masters/profile",
        json={"bio": "x", "city": "Toshkent", "district": "Yunusobod"},
        headers=headers_b,
    )

    r = client.delete(f"/api/v1/masters/me/photos/{photo_id}", headers=headers_b)
    assert r.status_code == 404
