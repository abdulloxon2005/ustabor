"""1. Access-control matrix va ownership (egalik) audit testlari."""

import pytest
from fastapi.routing import APIRoute

from app import models
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

DOCS_PATHS = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}
HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}

# Har bir marshrut uchun ruxsat etilgan rollar jadvali:
# "public" -> hamma (shu jumladan anonim) kira oladi
# set[str] -> faqat ko'rsatilgan rollar kira oladi
PERMISSION_TABLE: dict[tuple[str, str], str | set[str]] = {
    # Public routes
    ("GET", "/"): "public",
    ("GET", "/api/v1/health"): "public",
    ("POST", "/api/v1/auth/register"): "public",
    ("POST", "/api/v1/auth/login"): "public",
    ("GET", "/api/v1/categories"): "public",
    ("GET", "/api/v1/masters"): "public",
    ("GET", "/api/v1/masters/{master_id}"): "public",
    ("GET", "/api/v1/masters/{master_id}/reviews"): "public",
    # Authenticated (all active roles)
    ("GET", "/api/v1/auth/me"): {"customer", "master", "admin"},
    # Master routes
    ("POST", "/api/v1/masters/profile"): {"master"},
    ("GET", "/api/v1/masters/me"): {"master"},
    ("PATCH", "/api/v1/masters/me"): {"master"},
    ("PUT", "/api/v1/masters/me/services"): {"master"},
    ("PATCH", "/api/v1/masters/me/availability"): {"master"},
    ("GET", "/api/v1/masters/me/orders"): {"master"},
    ("GET", "/api/v1/masters/me/earnings"): {"master"},
    # Customer order routes
    ("POST", "/api/v1/orders"): {"customer"},
    ("GET", "/api/v1/orders"): {"customer"},
    ("GET", "/api/v1/orders/{order_id}"): {"customer"},
    ("POST", "/api/v1/orders/{order_id}/cancel"): {"customer"},
    ("POST", "/api/v1/orders/{order_id}/select-master"): {"customer"},
    ("POST", "/api/v1/orders/{order_id}/quotes/{quote_id}/accept"): {"customer"},
    ("POST", "/api/v1/orders/{order_id}/quotes/{quote_id}/reject"): {"customer"},
    ("POST", "/api/v1/orders/{order_id}/review"): {"customer"},
    # Master order action routes
    ("POST", "/api/v1/orders/{order_id}/accept"): {"master"},
    ("POST", "/api/v1/orders/{order_id}/reject"): {"master"},
    ("POST", "/api/v1/orders/{order_id}/quotes"): {"master"},
    ("POST", "/api/v1/orders/{order_id}/start"): {"master"},
    ("POST", "/api/v1/orders/{order_id}/complete"): {"master"},
    # Admin routes
    ("POST", "/api/v1/admin/categories"): {"admin"},
    ("PATCH", "/api/v1/admin/categories/{category_id}"): {"admin"},
    ("PATCH", "/api/v1/admin/masters/{profile_id}/approval"): {"admin"},
    ("GET", "/api/v1/admin/orders"): {"admin"},
    ("GET", "/api/v1/admin/orders/{order_id}"): {"admin"},
    ("PATCH", "/api/v1/admin/orders/{order_id}/assign"): {"admin"},
    ("POST", "/api/v1/admin/orders/{order_id}/cancel"): {"admin"},
    ("GET", "/api/v1/admin/users"): {"admin"},
    ("PATCH", "/api/v1/admin/users/{user_id}/status"): {"admin"},
    ("GET", "/api/v1/admin/commissions"): {"admin"},
}


def _collect_app_routes() -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for route in app.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if not path or not methods or path in DOCS_PATHS:
            continue
        for method in methods:
            if method in HTTP_METHODS:
                found.add((method, path))
    for path, path_item in app.openapi().get("paths", {}).items():
        if path in DOCS_PATHS:
            continue
        for method in path_item.keys():
            m_upper = method.upper()
            if m_upper in HTTP_METHODS:
                found.add((m_upper, path))
    return found


def test_guard_every_route_has_permission_entry():
    """Guard test: har bir FastAPI marshruti PERMISSION_TABLE da bo'lishi shart."""
    app_routes = _collect_app_routes()
    table_routes = set(PERMISSION_TABLE.keys())

    missing = app_routes - table_routes
    assert not missing, f"new route without a permission entry: {sorted(missing)}"

    extra = table_routes - app_routes
    assert not extra, f"stale permission entry for non-existent route: {sorted(extra)}"


@pytest.fixture
def perm_env(db, auth_header):
    """Barcha marshrutlarni haqiqiy ob'ektlar bilan tekshirish uchun muhit."""
    cat = models.Category(name="Santexnik", slug="santexnik", is_active=True)
    db.add(cat)

    customer = models.User(
        phone="+998901000001",
        password_hash=_PASSWORD_HASH,
        full_name="Mijoz A",
        role=Role.CUSTOMER,
        is_active=True,
    )
    master_user = models.User(
        phone="+998901000002",
        password_hash=_PASSWORD_HASH,
        full_name="Usta A",
        role=Role.MASTER,
        is_active=True,
    )
    admin = models.User(
        phone="+998901000003",
        password_hash=_PASSWORD_HASH,
        full_name="Admin",
        role=Role.ADMIN,
        is_active=True,
    )
    blocked_user = models.User(
        phone="+998901000004",
        password_hash=_PASSWORD_HASH,
        full_name="Bloklangan",
        role=Role.CUSTOMER,
        is_active=False,
    )
    db.add_all([customer, master_user, admin, blocked_user])
    db.flush()

    master_profile = models.MasterProfile(
        user_id=master_user.id,
        bio="Tajribali usta",
        city="Toshkent",
        district="Chilonzor",
        is_approved=True,
        is_available=True,
    )
    db.add(master_profile)
    db.flush()

    svc = models.MasterService(
        master_id=master_profile.id,
        category_id=cat.id,
        pricing_type=PricingType.QUOTE,
        base_price=None,
    )
    db.add(svc)

    order = models.Order(
        customer_id=customer.id,
        category_id=cat.id,
        master_id=master_profile.id,
        description="Quvur suv oqmoqda, tezda tuzatish kerak",
        city="Toshkent",
        district="Chilonzor",
        address="Chilonzor 9-kvartal, 12-uy",
        status=OrderStatus.ASSIGNED,
        selection_mode=SelectionMode.MANUAL,
        agreed_price=None,
        commission_rate=10,
    )
    db.add(order)
    db.flush()

    offer = models.OrderOffer(
        order_id=order.id,
        master_id=master_profile.id,
        status=OfferStatus.PENDING,
    )
    quote = models.Quote(
        order_id=order.id,
        master_id=master_profile.id,
        price=150_000,
        note="Ehtiyot qismlar bilan",
        status=QuoteStatus.PROPOSED,
    )
    db.add_all([offer, quote])
    db.commit()

    return {
        "cat_id": cat.id,
        "customer_id": customer.id,
        "master_user_id": master_user.id,
        "master_profile_id": master_profile.id,
        "order_id": order.id,
        "quote_id": quote.id,
        "headers": {
            "customer": auth_header(create_access_token(customer.id)),
            "master": auth_header(create_access_token(master_user.id)),
            "admin": auth_header(create_access_token(admin.id)),
            "blocked": auth_header(create_access_token(blocked_user.id)),
            "garbage": {"Authorization": "Bearer garbage.invalid.token"},
        },
    }


def _render_request(
    method: str, path_template: str, env: dict
) -> tuple[str, dict | list | None]:
    path = (
        path_template.replace("{master_id}", str(env["master_profile_id"]))
        .replace("{profile_id}", str(env["master_profile_id"]))
        .replace("{order_id}", str(env["order_id"]))
        .replace("{quote_id}", str(env["quote_id"]))
        .replace("{category_id}", str(env["cat_id"]))
        .replace("{user_id}", str(env["customer_id"]))
    )

    bodies: dict[tuple[str, str], dict | list] = {
        ("POST", "/api/v1/auth/register"): {
            "phone": "+998909998877",
            "password": "password123",
            "full_name": "Yangi Foydalanuvchi",
            "role": "customer",
        },
        ("POST", "/api/v1/auth/login"): {
            "phone": "+998901000001",
            "password": "secret123",
        },
        ("POST", "/api/v1/masters/profile"): {
            "bio": "Usta bio",
            "city": "Toshkent",
            "district": "Yunusobod",
        },
        ("PATCH", "/api/v1/masters/me"): {
            "bio": "Yangilangan bio",
        },
        ("PUT", "/api/v1/masters/me/services"): [
            {
                "category_id": env["cat_id"],
                "pricing_type": "quote",
                "base_price": None,
            }
        ],
        ("PATCH", "/api/v1/masters/me/availability"): {
            "is_available": True,
        },
        ("POST", "/api/v1/orders"): {
            "category_id": env["cat_id"],
            "description": "Kran suv oqizyapti, almashtirish kerak",
            "city": "Toshkent",
            "district": "Chilonzor",
            "address": "1-kvartal, 5-uy",
            "selection_mode": "manual",
        },
        ("POST", "/api/v1/orders/{order_id}/select-master"): {
            "master_id": env["master_profile_id"],
        },
        ("POST", "/api/v1/orders/{order_id}/quotes"): {
            "price": 200_000,
            "note": "Standart narx",
        },
        ("POST", "/api/v1/orders/{order_id}/review"): {
            "rating": 5,
            "comment": "A'lo darajada",
        },
        ("POST", "/api/v1/admin/categories"): {
            "name": "Elektrik",
            "slug": "elektrik",
        },
        ("PATCH", "/api/v1/admin/categories/{category_id}"): {
            "name": "Santexnik Pro",
            "is_active": True,
        },
        ("PATCH", "/api/v1/admin/masters/{profile_id}/approval"): {
            "is_approved": True,
        },
        ("PATCH", "/api/v1/admin/orders/{order_id}/assign"): {
            "master_id": env["master_profile_id"],
        },
        ("PATCH", "/api/v1/admin/users/{user_id}/status"): {
            "is_active": True,
        },
    }
    return path, bodies.get((method, path_template))


@pytest.mark.parametrize(
    "method,path_template,allowed",
    [(m, p, a) for (m, p), a in PERMISSION_TABLE.items()],
)
def test_route_permission_matrix(client, perm_env, method, path_template, allowed):
    """Har bir marshrut uchun anonim, buzuq token, bloklangan foydalanuvchi,
    noto'g'ri rol va to'g'ri rol tekshiruvi."""
    url, body = _render_request(method, path_template, perm_env)
    req_kwargs = {"json": body} if body is not None else {}

    if allowed == "public":
        r = client.request(method, url, **req_kwargs)
        assert r.status_code not in (401, 403), (
            f"Public route {method} {path_template} returned {r.status_code}: {r.text}"
        )
        return

    all_roles = {"customer", "master", "admin"}

    # 1. Anonymous -> 401
    r_anon = client.request(method, url, **req_kwargs)
    assert r_anon.status_code == 401, (
        f"{method} {path_template} anonymous expected 401, got {r_anon.status_code}"
    )

    # 2. Garbage token -> 401
    r_garbage = client.request(
        method, url, headers=perm_env["headers"]["garbage"], **req_kwargs
    )
    assert r_garbage.status_code == 401, (
        f"{method} {path_template} garbage token expected 401, got {r_garbage.status_code}"
    )

    # 3. Blocked user's token -> 401
    r_blocked = client.request(
        method, url, headers=perm_env["headers"]["blocked"], **req_kwargs
    )
    assert r_blocked.status_code == 401, (
        f"{method} {path_template} blocked user expected 401, got {r_blocked.status_code}"
    )

    # 4. Wrong roles -> 403
    for wrong_role in sorted(all_roles - set(allowed)):
        r_wrong = client.request(
            method, url, headers=perm_env["headers"][wrong_role], **req_kwargs
        )
        assert r_wrong.status_code == 403, (
            f"{method} {path_template} role={wrong_role} expected 403, got {r_wrong.status_code}: {r_wrong.text}"
        )

    # 5. Correct roles -> must NOT be 401 or 403
    for ok_role in sorted(allowed):
        r_ok = client.request(
            method, url, headers=perm_env["headers"][ok_role], **req_kwargs
        )
        assert r_ok.status_code not in (401, 403), (
            f"{method} {path_template} role={ok_role} got {r_ok.status_code}: {r_ok.text}"
        )


def test_ownership_customer_b_cannot_access_customer_a_order(
    client, db, auth_header, make_category
):
    """Customer B cannot get, cancel, select a master for, review, or accept/reject quotes on customer A's order (404)."""
    cat = make_category()

    cust_a = models.User(
        phone="+998902000001",
        password_hash=_PASSWORD_HASH,
        full_name="Mijoz A",
        role=Role.CUSTOMER,
    )
    cust_b = models.User(
        phone="+998902000002",
        password_hash=_PASSWORD_HASH,
        full_name="Mijoz B",
        role=Role.CUSTOMER,
    )
    master_u = models.User(
        phone="+998902000003",
        password_hash=_PASSWORD_HASH,
        full_name="Usta A",
        role=Role.MASTER,
    )
    db.add_all([cust_a, cust_b, master_u])
    db.flush()

    mp = models.MasterProfile(
        user_id=master_u.id,
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
        )
    )

    order_a = models.Order(
        customer_id=cust_a.id,
        category_id=cat.id,
        master_id=mp.id,
        description="Mijoz A buyurtmasi",
        city="Toshkent",
        district="Chilonzor",
        address="Manzil A",
        status=OrderStatus.ASSIGNED,
        selection_mode=SelectionMode.MANUAL,
        commission_rate=10,
    )
    db.add(order_a)
    db.flush()

    quote_a = models.Quote(
        order_id=order_a.id,
        master_id=mp.id,
        price=120_000,
        status=QuoteStatus.PROPOSED,
    )
    db.add(quote_a)
    db.commit()

    headers_b = auth_header(create_access_token(cust_b.id))

    # GET order -> 404
    assert client.get(f"/api/v1/orders/{order_a.id}", headers=headers_b).status_code == 404
    # Cancel -> 404
    assert client.post(f"/api/v1/orders/{order_a.id}/cancel", headers=headers_b).status_code == 404
    # Select master -> 404
    assert (
        client.post(
            f"/api/v1/orders/{order_a.id}/select-master",
            json={"master_id": mp.id},
            headers=headers_b,
        ).status_code
        == 404
    )
    # Accept quote -> 404
    assert (
        client.post(
            f"/api/v1/orders/{order_a.id}/quotes/{quote_a.id}/accept",
            headers=headers_b,
        ).status_code
        == 404
    )
    # Reject quote -> 404
    assert (
        client.post(
            f"/api/v1/orders/{order_a.id}/quotes/{quote_a.id}/reject",
            headers=headers_b,
        ).status_code
        == 404
    )
    # Review -> 404
    assert (
        client.post(
            f"/api/v1/orders/{order_a.id}/review",
            json={"rating": 5, "comment": "Zo'r"},
            headers=headers_b,
        ).status_code
        == 404
    )

    # Customer B's order list must not include Customer A's order
    r_list = client.get("/api/v1/orders", headers=headers_b)
    assert r_list.status_code == 200
    assert r_list.json() == []


def test_ownership_master_b_cannot_touch_master_a_order_or_see_earnings_and_offers(
    client, db, auth_header, make_category
):
    """Master B (not assigned, no offer) cannot accept, reject, quote, start or complete master A's order (404).
    Master B cannot see master A's earnings or offers.
    """
    cat = make_category()

    cust = models.User(
        phone="+998903000001",
        password_hash=_PASSWORD_HASH,
        full_name="Mijoz",
        role=Role.CUSTOMER,
    )
    master_a_u = models.User(
        phone="+998903000002",
        password_hash=_PASSWORD_HASH,
        full_name="Usta A",
        role=Role.MASTER,
    )
    master_b_u = models.User(
        phone="+998903000003",
        password_hash=_PASSWORD_HASH,
        full_name="Usta B",
        role=Role.MASTER,
    )
    db.add_all([cust, master_a_u, master_b_u])
    db.flush()

    mp_a = models.MasterProfile(
        user_id=master_a_u.id,
        city="Toshkent",
        district="Chilonzor",
        is_approved=True,
        is_available=True,
    )
    mp_b = models.MasterProfile(
        user_id=master_b_u.id,
        city="Toshkent",
        district="Chilonzor",
        is_approved=True,
        is_available=True,
    )
    db.add_all([mp_a, mp_b])
    db.flush()

    for mp in (mp_a, mp_b):
        db.add(
            models.MasterService(
                master_id=mp.id,
                category_id=cat.id,
                pricing_type=PricingType.QUOTE,
            )
        )

    # 1) Buyurtma searching holatda, faqat Master A ga taklif bor
    order_searching = models.Order(
        customer_id=cust.id,
        category_id=cat.id,
        description="Searching buyurtma",
        city="Toshkent",
        district="Chilonzor",
        address="Manzil 1",
        status=OrderStatus.SEARCHING,
        selection_mode=SelectionMode.MANUAL,
        commission_rate=10,
    )
    # 2) Buyurtma Master A ga biriktirilgan
    order_assigned = models.Order(
        customer_id=cust.id,
        category_id=cat.id,
        master_id=mp_a.id,
        description="Assigned buyurtma",
        city="Toshkent",
        district="Chilonzor",
        address="Manzil 2",
        status=OrderStatus.ASSIGNED,
        selection_mode=SelectionMode.MANUAL,
        agreed_price=200_000,
        commission_rate=10,
    )
    # 3) Buyurtma Master A tomonidan yakunlangan (daromad uchun)
    order_completed = models.Order(
        customer_id=cust.id,
        category_id=cat.id,
        master_id=mp_a.id,
        description="Completed buyurtma",
        city="Toshkent",
        district="Chilonzor",
        address="Manzil 3",
        status=OrderStatus.COMPLETED,
        selection_mode=SelectionMode.MANUAL,
        agreed_price=300_000,
        commission_rate=10,
        commission_amount=30_000,
    )
    db.add_all([order_searching, order_assigned, order_completed])
    db.flush()

    offer_a = models.OrderOffer(
        order_id=order_searching.id,
        master_id=mp_a.id,
        status=OfferStatus.PENDING,
    )
    db.add(offer_a)
    db.commit()

    headers_b = auth_header(create_access_token(master_b_u.id))

    # Master B cannot accept or reject Master A's offer -> 404
    assert client.post(f"/api/v1/orders/{order_searching.id}/accept", headers=headers_b).status_code == 404
    assert client.post(f"/api/v1/orders/{order_searching.id}/reject", headers=headers_b).status_code == 404

    # Master B cannot quote, start, or complete Master A's order -> 404
    assert (
        client.post(
            f"/api/v1/orders/{order_assigned.id}/quotes",
            json={"price": 150_000, "note": "B taklifi"},
            headers=headers_b,
        ).status_code
        == 404
    )
    assert client.post(f"/api/v1/orders/{order_assigned.id}/start", headers=headers_b).status_code == 404
    assert client.post(f"/api/v1/orders/{order_assigned.id}/complete", headers=headers_b).status_code == 404

    # Master B cannot see Master A's offers or active orders
    r_orders_b = client.get("/api/v1/masters/me/orders", headers=headers_b)
    assert r_orders_b.status_code == 200
    body_orders_b = r_orders_b.json()
    assert body_orders_b["pending_offers"] == []
    assert body_orders_b["active_orders"] == []

    # Master B cannot see Master A's earnings
    r_earn_b = client.get("/api/v1/masters/me/earnings", headers=headers_b)
    assert r_earn_b.status_code == 200
    body_earn_b = r_earn_b.json()
    assert body_earn_b["completed_count"] == 0
    assert body_earn_b["gross_total"] == 0
    assert body_earn_b["commission_total"] == 0
    assert body_earn_b["net_total"] == 0
    assert body_earn_b["orders"] == []


def test_customer_cannot_reach_any_masters_me_or_admin_routes(client, perm_env):
    """A customer cannot reach any /masters/me/* or /admin/* route."""
    cust_headers = perm_env["headers"]["customer"]

    for (method, path_template), allowed in PERMISSION_TABLE.items():
        if path_template.startswith("/api/v1/masters/me") or path_template.startswith("/api/v1/admin"):
            url, body = _render_request(method, path_template, perm_env)
            req_kwargs = {"json": body} if body is not None else {}
            r = client.request(method, url, headers=cust_headers, **req_kwargs)
            assert r.status_code == 403, f"Customer reached {method} {path_template}: {r.status_code}"
