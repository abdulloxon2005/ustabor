"""2. Kirish ma'lumotlarini tekshirish (input validation) va 500 xatolar yo'qligi auditi."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import models
from app.core.config import MAX_DB_INT
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.enums import (
    OfferStatus,
    OrderStatus,
    PricingType,
    QuoteStatus,
    Role,
    SelectionMode,
)

_PASSWORD_HASH = hash_password("secret123")
SQLI_STR = "'; DROP TABLE users;--"
XSS_STR = "<script>alert(1)</script>"
EMOJI_STR = "Usta 🔧✨ O'zbekiston — G'afur G'ulom ko'chasi"
OVERLONG_STR = "x" * 10_000


@pytest.fixture
def vclient(db):
    """Server xatolarini 500 status kodi sifatida qaytaradigan TestClient."""
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def val_env(db, auth_header):
    """Validation testlari uchun tayyor foydalanuvchilar va ob'ektlar."""
    cat = models.Category(name="Santexnik", slug="santexnik", is_active=True)
    db.add(cat)

    customer = models.User(
        phone="+998901110001",
        password_hash=_PASSWORD_HASH,
        full_name="Mijoz Val",
        role=Role.CUSTOMER,
        is_active=True,
    )
    master_no_prof = models.User(
        phone="+998901110002",
        password_hash=_PASSWORD_HASH,
        full_name="Usta Profilsiz",
        role=Role.MASTER,
        is_active=True,
    )
    master_with_prof = models.User(
        phone="+998901110003",
        password_hash=_PASSWORD_HASH,
        full_name="Usta Profilli",
        role=Role.MASTER,
        is_active=True,
    )
    admin = models.User(
        phone="+998901110004",
        password_hash=_PASSWORD_HASH,
        full_name="Admin Val",
        role=Role.ADMIN,
        is_active=True,
    )
    db.add_all([customer, master_no_prof, master_with_prof, admin])
    db.flush()

    mp = models.MasterProfile(
        user_id=master_with_prof.id,
        bio="Tajribali usta",
        city="Toshkent",
        district="Chilonzor",
        is_approved=True,
        is_available=True,
    )
    db.add(mp)
    db.flush()

    db.add(
        models.MasterService(
            master_id=mp.id,
            category_id=cat.id,
            pricing_type=PricingType.QUOTE,
            base_price=None,
        )
    )

    order_searching = models.Order(
        customer_id=customer.id,
        category_id=cat.id,
        description="Searching buyurtma",
        city="Toshkent",
        district="Chilonzor",
        address="Manzil 1",
        status=OrderStatus.SEARCHING,
        selection_mode=SelectionMode.MANUAL,
        commission_rate=10,
    )
    order_assigned = models.Order(
        customer_id=customer.id,
        category_id=cat.id,
        master_id=mp.id,
        description="Assigned buyurtma",
        city="Toshkent",
        district="Chilonzor",
        address="Manzil 2",
        status=OrderStatus.ASSIGNED,
        selection_mode=SelectionMode.MANUAL,
        commission_rate=10,
    )
    order_completed = models.Order(
        customer_id=customer.id,
        category_id=cat.id,
        master_id=mp.id,
        description="Completed buyurtma",
        city="Toshkent",
        district="Chilonzor",
        address="Manzil 3",
        status=OrderStatus.COMPLETED,
        selection_mode=SelectionMode.MANUAL,
        agreed_price=150_000,
        commission_rate=10,
        commission_amount=15_000,
    )
    db.add_all([order_searching, order_assigned, order_completed])
    db.flush()

    quote = models.Quote(
        order_id=order_assigned.id,
        master_id=mp.id,
        price=150_000,
        status=QuoteStatus.PROPOSED,
    )
    db.add(quote)
    db.commit()

    return {
        "cat_id": cat.id,
        "customer_id": customer.id,
        "master_profile_id": mp.id,
        "order_searching_id": order_searching.id,
        "order_assigned_id": order_assigned.id,
        "order_completed_id": order_completed.id,
        "quote_id": quote.id,
        "headers": {
            "public": {},
            "customer": auth_header(create_access_token(customer.id)),
            "master_no_prof": auth_header(create_access_token(master_no_prof.id)),
            "master": auth_header(create_access_token(master_with_prof.id)),
            "admin": auth_header(create_access_token(admin.id)),
        },
    }


def _db_counts(db) -> dict[str, int]:
    return {
        "users": db.scalar(select(func.count(models.User.id))),
        "categories": db.scalar(select(func.count(models.Category.id))),
        "profiles": db.scalar(select(func.count(models.MasterProfile.id))),
        "services": db.scalar(select(func.count(models.MasterService.id))),
        "orders": db.scalar(select(func.count(models.Order.id))),
        "offers": db.scalar(select(func.count(models.OrderOffer.id))),
        "quotes": db.scalar(select(func.count(models.Quote.id))),
        "reviews": db.scalar(select(func.count(models.Review.id))),
    }


# ==================== 2a. Body validation across all body endpoints ====================


def _body_endpoint_invalid_cases(env: dict) -> list[tuple[str, str, str, list]]:
    """(method, url, role_key, list_of_invalid_payloads) — barcha 4xx qaytarishi shart."""
    c_id = env["cat_id"]
    m_id = env["master_profile_id"]
    o_search = env["order_searching_id"]
    o_assign = env["order_assigned_id"]
    o_comp = env["order_completed_id"]
    u_id = env["customer_id"]

    return [
        (
            "POST",
            "/api/v1/auth/register",
            "public",
            [
                "__EMPTY_BODY__",
                {},
                {"phone": "+998901234567"},  # missing required
                {"phone": 998901234567, "password": "password123", "full_name": "Ali", "role": "customer"},
                {"phone": "+998901234567", "password": 12345678, "full_name": "Ali", "role": "customer"},
                {"phone": "+998901234567", "password": "password123", "full_name": 123, "role": "customer"},
                {"phone": "+998901234567", "password": "password123", "full_name": ["Ali"], "role": "customer"},
                {"phone": None, "password": "password123", "full_name": "Ali", "role": "customer"},
                {"phone": True, "password": "password123", "full_name": "Ali", "role": "customer"},
                {"phone": "", "password": "password123", "full_name": "Ali", "role": "customer"},
                {"phone": "   ", "password": "password123", "full_name": "Ali", "role": "customer"},
                {"phone": "+998901234567", "password": "password123", "full_name": "   ", "role": "customer"},
                {"phone": "+998901234567", "password": "password123", "full_name": OVERLONG_STR, "role": "customer"},
                {"phone": "+998901234567", "password": OVERLONG_STR, "full_name": "Ali Valiyev", "role": "customer"},
                {"phone": SQLI_STR, "password": "password123", "full_name": "Ali Valiyev", "role": "customer"},
                {"phone": XSS_STR, "password": "password123", "full_name": "Ali Valiyev", "role": "customer"},
            ],
        ),
        (
            "POST",
            "/api/v1/auth/login",
            "public",
            [
                "__EMPTY_BODY__",
                {},
                {"phone": "+998901110001"},
                {"password": "secret123"},
                {"phone": 998901110001, "password": "secret123"},
                {"phone": "+998901110001", "password": 12345678},
                {"phone": "+998901110001", "password": ["secret123"]},
                {"phone": "+998901110001", "password": None},
                {"phone": "+998901110001", "password": True},
                {"phone": "", "password": "secret123"},
                {"phone": "   ", "password": "secret123"},
                {"phone": "+998901110001", "password": ""},
                {"phone": "+998901110001", "password": OVERLONG_STR},
                {"phone": SQLI_STR, "password": "secret123"},
                {"phone": XSS_STR, "password": "secret123"},
            ],
        ),
        (
            "POST",
            "/api/v1/masters/profile",
            "master_no_prof",
            [
                "__EMPTY_BODY__",
                {},
                {"city": "Toshkent"},  # missing district
                {"district": "Chilonzor"},  # missing city
                {"bio": 123, "city": "Toshkent", "district": "Chilonzor"},
                {"bio": "ok", "city": 123, "district": "Chilonzor"},
                {"bio": "ok", "city": ["Toshkent"], "district": "Chilonzor"},
                {"bio": "ok", "city": None, "district": "Chilonzor"},
                {"bio": "ok", "city": True, "district": "Chilonzor"},
                {"bio": "ok", "city": "", "district": "Chilonzor"},
                {"bio": "ok", "city": "   ", "district": "Chilonzor"},
                {"bio": "ok", "city": "Toshkent", "district": "   "},
                {"bio": OVERLONG_STR, "city": "Toshkent", "district": "Chilonzor"},
                {"bio": "ok", "city": OVERLONG_STR, "district": "Chilonzor"},
                {"bio": "ok", "city": "Toshkent", "district": OVERLONG_STR},
            ],
        ),
        (
            "PATCH",
            "/api/v1/masters/me",
            "master",
            [
                "__EMPTY_BODY__",
                {"city": 123},
                {"district": ["Chilonzor"]},
                {"bio": None},
                {"city": None},
                {"district": None},
                {"city": True},
                {"city": ""},
                {"city": "   "},
                {"district": ""},
                {"district": "   "},
                {"bio": OVERLONG_STR},
                {"city": OVERLONG_STR},
                {"district": OVERLONG_STR},
            ],
        ),
        (
            "PUT",
            "/api/v1/masters/me/services",
            "master",
            [
                "__EMPTY_BODY__",
                {},
                [{}],
                [{"category_id": c_id}],
                [{"category_id": "abc", "pricing_type": "quote"}],
                [{"category_id": True, "pricing_type": "quote"}],
                [{"category_id": None, "pricing_type": "quote"}],
                [{"category_id": [c_id], "pricing_type": "quote"}],
                [{"category_id": c_id, "pricing_type": 123}],
                [{"category_id": c_id, "pricing_type": ""}],
                [{"category_id": c_id, "pricing_type": "   "}],
                [{"category_id": c_id, "pricing_type": OVERLONG_STR}],
                [{"category_id": c_id, "pricing_type": SQLI_STR}],
                [{"category_id": c_id, "pricing_type": XSS_STR}],
            ],
        ),
        (
            "PATCH",
            "/api/v1/masters/me/availability",
            "master",
            [
                "__EMPTY_BODY__",
                {},
                {"is_available": "true"},
                {"is_available": 1},
                {"is_available": None},
                {"is_available": [True]},
                {"is_available": ""},
                {"is_available": SQLI_STR},
                {"is_available": XSS_STR},
            ],
        ),
        (
            "POST",
            "/api/v1/orders",
            "customer",
            [
                "__EMPTY_BODY__",
                {},
                {"category_id": c_id, "description": "Suv oqmoqda"},
                {
                    "category_id": "1",
                    "description": "Quvur yorildi",
                    "city": "Toshkent",
                    "district": "Chilonzor",
                    "address": "1-uy",
                    "selection_mode": "manual",
                },
                {
                    "category_id": True,
                    "description": "Quvur yorildi",
                    "city": "Toshkent",
                    "district": "Chilonzor",
                    "address": "1-uy",
                    "selection_mode": "manual",
                },
                {
                    "category_id": None,
                    "description": "Quvur yorildi",
                    "city": "Toshkent",
                    "district": "Chilonzor",
                    "address": "1-uy",
                    "selection_mode": "manual",
                },
                {
                    "category_id": [c_id],
                    "description": "Quvur yorildi",
                    "city": "Toshkent",
                    "district": "Chilonzor",
                    "address": "1-uy",
                    "selection_mode": "manual",
                },
                {
                    "category_id": c_id,
                    "description": 123456,
                    "city": "Toshkent",
                    "district": "Chilonzor",
                    "address": "1-uy",
                    "selection_mode": "manual",
                },
                {
                    "category_id": c_id,
                    "description": "     ",
                    "city": "Toshkent",
                    "district": "Chilonzor",
                    "address": "1-uy",
                    "selection_mode": "manual",
                },
                {
                    "category_id": c_id,
                    "description": "Quvur yorildi",
                    "city": "   ",
                    "district": "Chilonzor",
                    "address": "1-uy",
                    "selection_mode": "manual",
                },
                {
                    "category_id": c_id,
                    "description": "Quvur yorildi",
                    "city": "Toshkent",
                    "district": "   ",
                    "address": "1-uy",
                    "selection_mode": "manual",
                },
                {
                    "category_id": c_id,
                    "description": "Quvur yorildi",
                    "city": "Toshkent",
                    "district": "Chilonzor",
                    "address": "   ",
                    "selection_mode": "manual",
                },
                {
                    "category_id": c_id,
                    "description": OVERLONG_STR,
                    "city": "Toshkent",
                    "district": "Chilonzor",
                    "address": "1-uy",
                    "selection_mode": "manual",
                },
                {
                    "category_id": c_id,
                    "description": "Quvur yorildi",
                    "city": OVERLONG_STR,
                    "district": "Chilonzor",
                    "address": "1-uy",
                    "selection_mode": "manual",
                },
                {
                    "category_id": c_id,
                    "description": "Quvur yorildi",
                    "city": "Toshkent",
                    "district": "Chilonzor",
                    "address": "1-uy",
                    "selection_mode": SQLI_STR,
                },
                {
                    "category_id": c_id,
                    "description": "Quvur yorildi",
                    "city": "Toshkent",
                    "district": "Chilonzor",
                    "address": "1-uy",
                    "selection_mode": XSS_STR,
                },
            ],
        ),
        (
            "POST",
            f"/api/v1/orders/{o_search}/select-master",
            "customer",
            [
                "__EMPTY_BODY__",
                {},
                {"master_id": "1"},
                {"master_id": True},
                {"master_id": None},
                {"master_id": [m_id]},
                {"master_id": ""},
                {"master_id": SQLI_STR},
                {"master_id": XSS_STR},
            ],
        ),
        (
            "POST",
            f"/api/v1/orders/{o_assign}/quotes",
            "master",
            [
                "__EMPTY_BODY__",
                {},
                {"note": "narxsiz"},
                {"price": "150000"},
                {"price": True},
                {"price": None},
                {"price": [150000]},
                {"price": 150000, "note": 12345},
                {"price": 150000, "note": OVERLONG_STR},
                {"price": SQLI_STR},
                {"price": XSS_STR},
            ],
        ),
        (
            "POST",
            f"/api/v1/orders/{o_comp}/review",
            "customer",
            [
                "__EMPTY_BODY__",
                {},
                {"comment": "bahosiz"},
                {"rating": "5"},
                {"rating": True},
                {"rating": None},
                {"rating": [5]},
                {"rating": 5, "comment": 123},
                {"rating": 5, "comment": ["yaxshi"]},
                {"rating": 5, "comment": OVERLONG_STR},
                {"rating": SQLI_STR},
                {"rating": XSS_STR},
            ],
        ),
        (
            "POST",
            "/api/v1/admin/categories",
            "admin",
            [
                "__EMPTY_BODY__",
                {},
                {"slug": "faqat-slug"},
                {"name": 123},
                {"name": ["Santexnik"]},
                {"name": None},
                {"name": True},
                {"name": ""},
                {"name": "   "},
                {"name": "a"},
                {"name": OVERLONG_STR},
                {"name": "Yangi", "slug": OVERLONG_STR},
                {"name": "Yangi", "slug": SQLI_STR},
                {"name": "Yangi", "slug": XSS_STR},
            ],
        ),
        (
            "PATCH",
            f"/api/v1/admin/categories/{c_id}",
            "admin",
            [
                "__EMPTY_BODY__",
                {"name": 123},
                {"name": ["Elektrik"]},
                {"name": ""},
                {"name": "   "},
                {"name": "a"},
                {"name": OVERLONG_STR},
                {"is_active": "not-a-bool"},
                {"is_active": [True]},
                {"is_active": SQLI_STR},
                {"is_active": XSS_STR},
            ],
        ),
        (
            "PATCH",
            f"/api/v1/admin/masters/{m_id}/approval",
            "admin",
            [
                "__EMPTY_BODY__",
                {},
                {"is_approved": "true"},
                {"is_approved": 1},
                {"is_approved": None},
                {"is_approved": [True]},
                {"is_approved": SQLI_STR},
                {"is_approved": XSS_STR},
            ],
        ),
        (
            "PATCH",
            f"/api/v1/admin/orders/{o_search}/assign",
            "admin",
            [
                "__EMPTY_BODY__",
                {},
                {"master_id": "1"},
                {"master_id": True},
                {"master_id": None},
                {"master_id": [m_id]},
                {"master_id": SQLI_STR},
                {"master_id": XSS_STR},
            ],
        ),
        (
            "PATCH",
            f"/api/v1/admin/users/{u_id}/status",
            "admin",
            [
                "__EMPTY_BODY__",
                {},
                {"is_active": "not-a-bool"},
                {"is_active": None},
                {"is_active": [False]},
                {"is_active": SQLI_STR},
                {"is_active": XSS_STR},
            ],
        ),
    ]


def test_all_body_endpoints_reject_invalid_inputs_with_4xx_and_create_nothing(
    vclient, db, val_env
):
    """2a: Har bir body qabul qiluvchi endpoint noto'g'ri ma'lumotlarda 4xx qaytaradi (5xx emas)
    va bazada hech narsa yaratilmaydi."""
    before = _db_counts(db)
    failures = []

    for method, url, role_key, payloads in _body_endpoint_invalid_cases(val_env):
        headers = val_env["headers"][role_key]
        for payload in payloads:
            if payload == "__EMPTY_BODY__":
                r = vclient.request(
                    method,
                    url,
                    content=b"",
                    headers={**headers, "Content-Type": "application/json"},
                )
            else:
                r = vclient.request(method, url, json=payload, headers=headers)

            if not (400 <= r.status_code < 500):
                failures.append((method, url, payload, r.status_code, r.text[:120]))

    after = _db_counts(db)
    assert after == before, f"Objects were created during invalid requests: {before} -> {after}"
    assert not failures, f"Body validation failures: {failures}"


def test_patch_endpoints_reject_empty_object(vclient, val_env):
    """2a: Empty object {} sent to PATCH endpoints should return 4xx."""
    r1 = vclient.patch("/api/v1/masters/me", json={}, headers=val_env["headers"]["master"])
    r2 = vclient.patch(
        f"/api/v1/admin/categories/{val_env['cat_id']}",
        json={},
        headers=val_env["headers"]["admin"],
    )
    assert 400 <= r1.status_code < 500 and 400 <= r2.status_code < 500


def test_admin_user_status_rejects_non_strict_bool(vclient, val_env):
    """2a: Wrong types (string 'true' or int 1 for bool) on PATCH /admin/users/{id}/status should return 422."""
    u_id = val_env["customer_id"]
    admin_h = val_env["headers"]["admin"]
    r_str = vclient.patch(
        f"/api/v1/admin/users/{u_id}/status",
        json={"is_active": "true"},
        headers=admin_h,
    )
    r_int = vclient.patch(
        f"/api/v1/admin/users/{u_id}/status",
        json={"is_active": 1},
        headers=admin_h,
    )
    assert r_str.status_code == 422 and r_int.status_code == 422


def test_unicode_emoji_and_sqli_strings_never_cause_500(vclient, db, val_env):
    """2a: Unicode/emoji, qo'shtirnoq va SQL ko'rinishidagi satrlar hech qachon 500 keltirib chiqarmaydi
    va users jadvali o'chib ketmaydi."""
    c_id = val_env["cat_id"]
    cust_headers = val_env["headers"]["customer"]

    for text_val in (EMOJI_STR, SQLI_STR, XSS_STR):
        r = vclient.post(
            "/api/v1/orders",
            json={
                "category_id": c_id,
                "description": f"Buyurtma tavsifi: {text_val}",
                "city": "Toshkent",
                "district": "Chilonzor",
                "address": text_val,
                "selection_mode": "manual",
            },
            headers=cust_headers,
        )
        assert r.status_code < 500, f"5xx on text {text_val!r}: {r.status_code} {r.text}"

    # Users table still intact
    assert db.scalar(select(func.count(models.User.id))) >= 4


# ==================== 2b. Path IDs ====================


@pytest.mark.parametrize(
    "bad_id",
    [
        0,
        -1,
        MAX_DB_INT + 1,
        99999999999999999999,
        "abc",
        "1.5",
    ],
)
def test_path_ids_return_404_or_422_never_500(vclient, val_env, bad_id):
    """2b: Path ids: 0, -1, 2147483648, 99999999999999999999, 'abc', '1.5' -> 404 or 422, never 500."""
    h = val_env["headers"]
    m_id = val_env["master_profile_id"]
    o_id = val_env["order_assigned_id"]

    cases = [
        ("GET", f"/api/v1/masters/{bad_id}", h["public"], None),
        ("GET", f"/api/v1/masters/{bad_id}/reviews", h["public"], None),
        ("GET", f"/api/v1/orders/{bad_id}", h["customer"], None),
        ("POST", f"/api/v1/orders/{bad_id}/cancel", h["customer"], None),
        (
            "POST",
            f"/api/v1/orders/{bad_id}/select-master",
            h["customer"],
            {"master_id": m_id},
        ),
        ("POST", f"/api/v1/orders/{bad_id}/accept", h["master"], None),
        ("POST", f"/api/v1/orders/{bad_id}/reject", h["master"], None),
        (
            "POST",
            f"/api/v1/orders/{bad_id}/quotes",
            h["master"],
            {"price": 100_000, "note": "ok"},
        ),
        (
            "POST",
            f"/api/v1/orders/{bad_id}/quotes/1/accept",
            h["customer"],
            None,
        ),
        (
            "POST",
            f"/api/v1/orders/{o_id}/quotes/{bad_id}/accept",
            h["customer"],
            None,
        ),
        (
            "POST",
            f"/api/v1/orders/{bad_id}/quotes/1/reject",
            h["customer"],
            None,
        ),
        (
            "POST",
            f"/api/v1/orders/{o_id}/quotes/{bad_id}/reject",
            h["customer"],
            None,
        ),
        ("POST", f"/api/v1/orders/{bad_id}/start", h["master"], None),
        ("POST", f"/api/v1/orders/{bad_id}/complete", h["master"], None),
        (
            "POST",
            f"/api/v1/orders/{bad_id}/review",
            h["customer"],
            {"rating": 5, "comment": "ok"},
        ),
        (
            "PATCH",
            f"/api/v1/admin/categories/{bad_id}",
            h["admin"],
            {"name": "Yangi nom"},
        ),
        (
            "PATCH",
            f"/api/v1/admin/masters/{bad_id}/approval",
            h["admin"],
            {"is_approved": True},
        ),
        ("GET", f"/api/v1/admin/orders/{bad_id}", h["admin"], None),
        ("POST", f"/api/v1/admin/orders/{bad_id}/cancel", h["admin"], None),
        (
            "PATCH",
            f"/api/v1/admin/orders/{bad_id}/assign",
            h["admin"],
            {"master_id": m_id},
        ),
        (
            "PATCH",
            f"/api/v1/admin/users/{bad_id}/status",
            h["admin"],
            {"is_active": False},
        ),
    ]

    failures = []
    for method, url, headers, body in cases:
        kw = {"json": body} if body is not None else {}
        r = vclient.request(method, url, headers=headers, **kw)
        if isinstance(bad_id, int) and bad_id > MAX_DB_INT:
            if r.status_code != 422:
                failures.append((method, url, r.status_code, r.text[:120]))
        elif r.status_code not in (404, 422):
            failures.append((method, url, r.status_code, r.text[:120]))

    assert not failures, f"Path ID validation failures for {bad_id!r}: {failures}"


def test_path_ids_accept_max_db_int_as_404_not_422(vclient, val_env):
    """2b: 2147483647 (MAX_DB_INT) is accepted by path bound validation and returns 404 (not 422/500)."""
    h = val_env["headers"]
    max_id = MAX_DB_INT
    for method, url, headers in [
        ("GET", f"/api/v1/masters/{max_id}", h["public"]),
        ("GET", f"/api/v1/orders/{max_id}", h["customer"]),
        ("GET", f"/api/v1/admin/orders/{max_id}", h["admin"]),
    ]:
        r = vclient.request(method, url, headers=headers)
        assert r.status_code == 404, f"{method} {url} -> {r.status_code}"


# ==================== 2c. Query params ====================


def test_query_params_clamping_and_validation_never_500(vclient, val_env):
    """2c: Query params: limit/offset negative, huge or non-numeric; invalid dates;
    unknown filter values -> 200 with sane clamping or 422, never 500."""
    h = val_env["headers"]
    m_id = val_env["master_profile_id"]

    paginated_endpoints = [
        (f"/api/v1/masters/{m_id}/reviews", h["public"]),
        ("/api/v1/orders", h["customer"]),
        ("/api/v1/admin/orders", h["admin"]),
        ("/api/v1/admin/users", h["admin"]),
        ("/api/v1/admin/commissions", h["admin"]),
    ]

    for url, headers in paginated_endpoints:
        # Negative and huge limit/offset -> 200 with sane clamping (or 422)
        for params in (
            {"limit": -10, "offset": -5},
            {"limit": 0, "offset": 0},
            {"limit": 100_000, "offset": 100_000},
        ):
            r = vclient.get(url, params=params, headers=headers)
            assert r.status_code in (200, 422), f"{url} {params} -> {r.status_code}"

        # Non-numeric limit/offset -> 422
        for bad_params in (
            {"limit": "abc"},
            {"offset": "xyz"},
            {"limit": "1.5"},
        ):
            r = vclient.get(url, params=bad_params, headers=headers)
            assert r.status_code == 422, f"{url} {bad_params} -> {r.status_code}"

    # Invalid dates on /admin/commissions -> 422
    for bad_date in ("not-a-date", "2026-13-45", "2026/01/01", "99-99-9999", SQLI_STR):
        r1 = vclient.get(
            "/api/v1/admin/commissions",
            params={"date_from": bad_date},
            headers=h["admin"],
        )
        r2 = vclient.get(
            "/api/v1/admin/commissions",
            params={"date_to": bad_date},
            headers=h["admin"],
        )
        assert r1.status_code == 422, f"date_from={bad_date} -> {r1.status_code}"
        assert r2.status_code == 422, f"date_to={bad_date} -> {r2.status_code}"

    # Unknown enum filter values -> 422
    assert (
        vclient.get(
            "/api/v1/orders",
            params={"status_filter": "unknown_status"},
            headers=h["customer"],
        ).status_code
        == 422
    )
    assert (
        vclient.get(
            "/api/v1/admin/orders",
            params={"status": "unknown_status"},
            headers=h["admin"],
        ).status_code
        == 422
    )
    assert (
        vclient.get(
            "/api/v1/admin/users",
            params={"role": "superadmin"},
            headers=h["admin"],
        ).status_code
        == 422
    )
    assert (
        vclient.get(
            "/api/v1/masters",
            params={"category_id": "not-an-int"},
        ).status_code
        == 422
    )


def test_huge_int_overflow_in_query_params_and_body_ids_never_500(vclient, val_env):
    """2c: 2147483648 and 99999999999999999999 in offset/filter query params and body IDs are rejected with 422;
    2147483647 (MAX_DB_INT) is accepted by the bound and never causes 500."""
    h = val_env["headers"]
    o_search = val_env["order_searching_id"]

    # 1. Rejected values (> MAX_DB_INT): 2147483648 and 99999999999999999999 -> 422
    for rejected in (MAX_DB_INT + 1, 99999999999999999999):
        responses = [
            vclient.get(f"/api/v1/masters/{val_env['master_profile_id']}/reviews", params={"offset": rejected}),
            vclient.get("/api/v1/masters", params={"category_id": rejected}),
            vclient.get("/api/v1/orders", params={"offset": rejected}, headers=h["customer"]),
            vclient.get("/api/v1/admin/orders", params={"offset": rejected}, headers=h["admin"]),
            vclient.get("/api/v1/admin/orders", params={"category_id": rejected}, headers=h["admin"]),
            vclient.get("/api/v1/admin/orders", params={"master_id": rejected}, headers=h["admin"]),
            vclient.get("/api/v1/admin/users", params={"offset": rejected}, headers=h["admin"]),
            vclient.get("/api/v1/admin/commissions", params={"offset": rejected}, headers=h["admin"]),
            vclient.post(
                "/api/v1/orders",
                json={
                    "category_id": rejected,
                    "description": "Santexnika ishi",
                    "city": "Toshkent",
                    "district": "Chilonzor",
                    "address": "1-uy",
                    "selection_mode": "manual",
                },
                headers=h["customer"],
            ),
            vclient.post(
                f"/api/v1/orders/{o_search}/select-master",
                json={"master_id": rejected},
                headers=h["customer"],
            ),
            vclient.put(
                "/api/v1/masters/me/services",
                json=[{"category_id": rejected, "pricing_type": "quote"}],
                headers=h["master"],
            ),
            vclient.patch(
                f"/api/v1/admin/orders/{o_search}/assign",
                json={"master_id": rejected},
                headers=h["admin"],
            ),
        ]
        assert all(r.status_code == 422 for r in responses), [
            (r.status_code, r.text[:80]) for r in responses
        ]

    # 2. Largest accepted value (MAX_DB_INT = 2147483647): query params return 200, body endpoints pass bound and return domain 404/422 (never 500)
    max_ok = MAX_DB_INT
    query_ok_responses = [
        vclient.get(f"/api/v1/masters/{val_env['master_profile_id']}/reviews", params={"offset": max_ok}),
        vclient.get("/api/v1/masters", params={"category_id": max_ok}),
        vclient.get("/api/v1/orders", params={"offset": max_ok}, headers=h["customer"]),
        vclient.get("/api/v1/admin/orders", params={"offset": max_ok}, headers=h["admin"]),
        vclient.get("/api/v1/admin/orders", params={"category_id": max_ok}, headers=h["admin"]),
        vclient.get("/api/v1/admin/orders", params={"master_id": max_ok}, headers=h["admin"]),
        vclient.get("/api/v1/admin/users", params={"offset": max_ok}, headers=h["admin"]),
        vclient.get("/api/v1/admin/commissions", params={"offset": max_ok}, headers=h["admin"]),
    ]
    assert all(r.status_code == 200 for r in query_ok_responses), [
        r.status_code for r in query_ok_responses
    ]

    r_assign_max = vclient.patch(
        f"/api/v1/admin/orders/{o_search}/assign",
        json={"master_id": max_ok},
        headers=h["admin"],
    )
    assert r_assign_max.status_code == 404  # passes schema bound, master not found in DB

    for r_body_max in (
        vclient.post(
            "/api/v1/orders",
            json={
                "category_id": max_ok,
                "description": "Santexnika ishi",
                "city": "Toshkent",
                "district": "Chilonzor",
                "address": "1-uy",
                "selection_mode": "manual",
            },
            headers=h["customer"],
        ),
        vclient.post(
            f"/api/v1/orders/{o_search}/select-master",
            json={"master_id": max_ok},
            headers=h["customer"],
        ),
        vclient.put(
            "/api/v1/masters/me/services",
            json=[{"category_id": max_ok, "pricing_type": "quote"}],
            headers=h["master"],
        ),
    ):
        assert r_body_max.status_code == 422
        assert isinstance(r_body_max.json().get("detail"), str)  # domain 422, not Pydantic bound error


# ==================== 2d. Money and numbers ====================


def test_money_and_number_validation(vclient, val_env):
    """2d: Money and numbers: price 0, negative, 1.5, '100', true, 10**15, base_price negative;
    rating 0, 6, true, 3.5; selection_mode and pricing_type with unknown values."""
    h = val_env["headers"]
    c_id = val_env["cat_id"]
    o_assign = val_env["order_assigned_id"]
    o_comp = val_env["order_completed_id"]

    # Quote price invalid values
    for bad_price in (0, -1, -100_000, 1.5, "100", True, False, 10**15):
        r = vclient.post(
            f"/api/v1/orders/{o_assign}/quotes",
            json={"price": bad_price, "note": "test"},
            headers=h["master"],
        )
        assert r.status_code == 422, f"quote price={bad_price!r} -> {r.status_code}"

    # Service base_price invalid values & pricing_type unknown values
    for bad_base in (0, -1, -50_000, 1.5, "100", True, False, 10**15):
        r = vclient.put(
            "/api/v1/masters/me/services",
            json=[{"category_id": c_id, "pricing_type": "fixed", "base_price": bad_base}],
            headers=h["master"],
        )
        assert r.status_code == 422, f"base_price={bad_base!r} -> {r.status_code}"

    for bad_pt in ("hourly", "free", "FIXED", "QUOTE", "unknown"):
        r = vclient.put(
            "/api/v1/masters/me/services",
            json=[{"category_id": c_id, "pricing_type": bad_pt, "base_price": 100_000}],
            headers=h["master"],
        )
        assert r.status_code == 422, f"pricing_type={bad_pt!r} -> {r.status_code}"

    # Rating invalid values
    for bad_rating in (0, -1, 6, 10, True, False, 3.5, "5"):
        r = vclient.post(
            f"/api/v1/orders/{o_comp}/review",
            json={"rating": bad_rating, "comment": "test"},
            headers=h["customer"],
        )
        assert r.status_code == 422, f"rating={bad_rating!r} -> {r.status_code}"

    # selection_mode unknown values
    for bad_mode in ("auto", "hand", "MANUAL", "AUTOMATIC", "random"):
        r = vclient.post(
            "/api/v1/orders",
            json={
                "category_id": c_id,
                "description": "Santexnika ishi kerak",
                "city": "Toshkent",
                "district": "Chilonzor",
                "address": "1-uy",
                "selection_mode": bad_mode,
            },
            headers=h["customer"],
        )
        assert r.status_code == 422, f"selection_mode={bad_mode!r} -> {r.status_code}"


# ==================== 2e. Registration validation ====================


def test_registration_validation_and_mass_assignment_protection(
    vclient, db, val_env
):
    """2e: Registration: weak/short password, phone in many formats, duplicate phone with
    different formatting, role 'admin', 'ADMIN', 'Master' (case), extra unknown fields
    (is_active, is_approved, rating_avg, commission_rate) are ignored or rejected and never applied."""
    # Short passwords
    for short_pw in ("", "123", "1234567"):
        r = vclient.post(
            "/api/v1/auth/register",
            json={
                "phone": "+998905551122",
                "password": short_pw,
                "full_name": "Test User",
                "role": "customer",
            },
        )
        assert r.status_code == 422, f"short_pw={short_pw!r} -> {r.status_code}"

    # Invalid phone formats
    for bad_phone in ("12345", "+79001234567", "+99890123456", "+9989012345678", "abc", "+99890123456a"):
        r = vclient.post(
            "/api/v1/auth/register",
            json={
                "phone": bad_phone,
                "password": "password123",
                "full_name": "Test User",
                "role": "customer",
            },
        )
        assert r.status_code == 422, f"bad_phone={bad_phone!r} -> {r.status_code}"

    # Valid phone in one format, then duplicate attempts in different formats -> 409
    r_ok = vclient.post(
        "/api/v1/auth/register",
        json={
            "phone": "90 777-88-99",
            "password": "password123",
            "full_name": "Birinchi User",
            "role": "customer",
        },
    )
    assert r_ok.status_code == 201
    assert r_ok.json()["user"]["phone"] == "+998907778899"

    for dup_phone in (
        "+998907778899",
        "998907778899",
        "907778899",
        "+998 (90) 777-88-99",
        "90-777-88-99",
    ):
        r_dup = vclient.post(
            "/api/v1/auth/register",
            json={
                "phone": dup_phone,
                "password": "password123",
                "full_name": "Dublikat User",
                "role": "customer",
            },
        )
        assert r_dup.status_code == 409, f"dup_phone={dup_phone!r} -> {r_dup.status_code}"

    # Disallowed roles and wrong case
    for bad_role in ("admin", "ADMIN", "Master", "Customer", "CUSTOMER", "MASTER"):
        r_role = vclient.post(
            "/api/v1/auth/register",
            json={
                "phone": "+998906661122",
                "password": "password123",
                "full_name": "Test Role",
                "role": bad_role,
            },
        )
        assert r_role.status_code == 422, f"bad_role={bad_role!r} -> {r_role.status_code}"

    # Extra unknown fields on register, profile create, order create
    r_extra = vclient.post(
        "/api/v1/auth/register",
        json={
            "phone": "+998906663344",
            "password": "password123",
            "full_name": "Extra Master",
            "role": "master",
            "is_active": False,
            "is_approved": True,
            "rating_avg": 5.0,
            "commission_rate": 0,
        },
    )
    assert r_extra.status_code == 201
    u_data = r_extra.json()["user"]
    assert u_data["is_active"] is True
    assert u_data["role"] == "master"


# ==================== 2f. Stored text round-trip ====================


def test_stored_text_round_trip_preserves_script_tag_unchanged(vclient, val_env):
    """2f: A customer name or order description containing <script> is returned as plain JSON
    text unchanged (no HTML escaping in the API, escaping is the frontend's job)."""
    name_with_script = "Ali <script>alert(1)</script> Valiyev"
    desc_with_script = "Kran buzildi <script>alert('xss')</script> & 'tez' tuzating"

    r_reg = vclient.post(
        "/api/v1/auth/register",
        json={
            "phone": "+998908889900",
            "password": "password123",
            "full_name": name_with_script,
            "role": "customer",
        },
    )
    assert r_reg.status_code == 201
    reg_body = r_reg.json()
    assert reg_body["user"]["full_name"] == name_with_script

    token = reg_body["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    r_me = vclient.get("/api/v1/auth/me", headers=headers)
    assert r_me.status_code == 200
    assert r_me.json()["full_name"] == name_with_script

    r_ord = vclient.post(
        "/api/v1/orders",
        json={
            "category_id": val_env["cat_id"],
            "description": desc_with_script,
            "city": "Toshkent",
            "district": "Chilonzor",
            "address": "12-uy <script>",
            "selection_mode": "manual",
        },
        headers=headers,
    )
    assert r_ord.status_code == 201
    ord_body = r_ord.json()
    assert ord_body["description"] == desc_with_script
    assert ord_body["address"] == "12-uy <script>"

    r_get = vclient.get(f"/api/v1/orders/{ord_body['id']}", headers=headers)
    assert r_get.status_code == 200
    assert r_get.json()["description"] == desc_with_script
