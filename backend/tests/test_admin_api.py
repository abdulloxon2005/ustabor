"""HTTP API testlar: Admin boshqaruv paneli (Admin API)."""

from datetime import datetime

import pytest
from sqlalchemy import select

from app import models
from app.models.enums import OrderStatus, PaymentMethod, PaymentStatus, PricingType, Role, SelectionMode
from app.services.order_flow import assign_master, transition


def _create_master_profile(
    db,
    user_id: int,
    cat_id: int,
    is_approved: bool = True,
    is_available: bool = True,
    pricing_type: PricingType = PricingType.FIXED,
    base_price: int | None = 150_000,
) -> models.MasterProfile:
    mp = models.MasterProfile(
        user_id=user_id,
        bio="Usta bio",
        city="Toshkent",
        district="Chilonzor",
        is_approved=is_approved,
        is_available=is_available,
    )
    db.add(mp)
    db.flush()
    ms = models.MasterService(
        master_id=mp.id,
        category_id=cat_id,
        pricing_type=pricing_type,
        base_price=base_price,
    )
    db.add(ms)
    db.commit()
    db.refresh(mp)
    return mp


def _create_order(client, cust_headers, cat_id, status: OrderStatus = OrderStatus.SEARCHING) -> int:
    r = client.post(
        "/api/v1/orders",
        json={
            "category_id": cat_id,
            "description": "Admin test buyurtmasi",
            "city": "Toshkent",
            "district": "Chilonzor",
            "address": "Mustaqillik 1",
            "selection_mode": "manual",
        },
        headers=cust_headers,
    )
    assert r.status_code == 201
    return r.json()["id"]


def test_admin_routes_auth_and_roles(client, db, signup, admin_headers, make_category):
    """Barcha /admin yo'llari: anonim 401, mijoz 403, usta 403, admin 200."""
    cat = make_category("Santexnik", "santexnik_adm_auth")
    h_c, u_c = signup("customer", "+998901230001", "Mijoz Auth")
    h_m, u_m = signup("master", "+998901230002", "Usta Auth")
    mp = _create_master_profile(db, u_m["id"], cat.id)
    order_id = _create_order(client, h_c, cat.id)

    routes = [
        ("GET", "/api/v1/admin/orders"),
        ("GET", f"/api/v1/admin/orders/{order_id}"),
        ("GET", "/api/v1/admin/users"),
        ("GET", "/api/v1/admin/commissions"),
    ]

    for method, path in routes:
        # Anonim -> 401
        r_anon = client.request(method, path)
        assert r_anon.status_code == 401, f"{path} anonim uchun 401 bo'lishi kerak, {r_anon.status_code} keldi"

        # Mijoz -> 403
        r_cust = client.request(method, path, headers=h_c)
        assert r_cust.status_code == 403, f"{path} mijoz uchun 403 bo'lishi kerak, {r_cust.status_code} keldi"

        # Usta -> 403
        r_mast = client.request(method, path, headers=h_m)
        assert r_mast.status_code == 403, f"{path} usta uchun 403 bo'lishi kerak, {r_mast.status_code} keldi"

        # Admin -> 200
        r_admin = client.request(method, path, headers=admin_headers)
        assert r_admin.status_code == 200, f"{path} admin uchun 200 bo'lishi kerak, {r_admin.status_code} keldi"


def test_admin_orders_filters_and_pagination(client, db, signup, admin_headers, make_category):
    cat1 = make_category("Santexnik", "santexnik_filt")
    cat2 = make_category("Elektrik", "elektrik_filt")
    h_c, u_c = signup("customer", "+998901230003", "Mijoz Filt")

    o1 = _create_order(client, h_c, cat1.id)
    o2 = _create_order(client, h_c, cat2.id)

    # Filter by category_id
    r1 = client.get(f"/api/v1/admin/orders?category_id={cat1.id}", headers=admin_headers)
    assert r1.status_code == 200
    orders1 = r1.json()
    assert all(o["category_id"] == cat1.id for o in orders1)
    assert any(o["id"] == o1 for o in orders1)

    # Filter by status
    r_stat = client.get("/api/v1/admin/orders?status=searching", headers=admin_headers)
    assert r_stat.status_code == 200
    assert all(o["status"] == "searching" for o in r_stat.json())

    # Pagination: limit=1, offset=0 and offset=1
    r_p1 = client.get("/api/v1/admin/orders?limit=1&offset=0", headers=admin_headers)
    r_p2 = client.get("/api/v1/admin/orders?limit=1&offset=1", headers=admin_headers)
    assert len(r_p1.json()) == 1
    assert len(r_p2.json()) == 1
    assert r_p1.json()[0]["id"] != r_p2.json()[0]["id"]

    # Har bir element talab qilingan barcha maydonlarni o'z ichiga oladi
    item = r_p1.json()[0]
    expected_keys = {
        "id", "status", "category", "category_name", "category_id",
        "customer_id", "customer_name", "customer_phone",
        "master_name", "city", "district", "agreed_price", "commission_amount", "created_at"
    }
    for k in expected_keys:
        assert k in item, f"{k} admin buyurtma ro'yxatida yo'q"


def test_admin_order_detail(client, db, signup, admin_headers, make_category):
    cat = make_category("Santexnik", "santexnik_det")
    h_c, u_c = signup("customer", "+998901230004", "Mijoz Det")
    order_id = _create_order(client, h_c, cat.id)

    r = client.get(f"/api/v1/admin/orders/{order_id}", headers=admin_headers)
    assert r.status_code == 200
    d = r.json()
    assert d["id"] == order_id
    assert d["status"] == "searching"
    assert "history" in d
    assert "offers" in d
    assert "quotes" in d
    assert "payment" in d
    assert "review" in d


def test_admin_users_endpoint_no_passwords_and_filters(client, db, signup, admin_headers, make_category):
    h_c, u_c = signup("customer", "+998901230005", "Nodir Salimov")
    h_m, u_m = signup("master", "+998901230006", "Sardor Rahimov")
    cat = make_category("Santexnik", "santexnik_usr")
    mp = _create_master_profile(db, u_m["id"], cat.id)

    r = client.get("/api/v1/admin/users", headers=admin_headers)
    assert r.status_code == 200
    users = r.json()
    assert len(users) >= 2

    for u in users:
        # Hech qachon parol yoki parol xeshi chiqmaydi
        assert "password" not in u
        assert "password_hash" not in u
        assert "hashed_password" not in u

    # Qidiruv filter: ?q=Nodir
    r_q = client.get("/api/v1/admin/users?q=Nodir", headers=admin_headers)
    assert r_q.status_code == 200
    q_res = r_q.json()
    assert any("Nodir" in u["full_name"] for u in q_res)

    # Rol filter: ?role=master
    r_role = client.get("/api/v1/admin/users?role=master", headers=admin_headers)
    assert r_role.status_code == 200
    for u in r_role.json():
        assert u["role"] == "master"
        assert "profile_id" in u
        assert "is_approved" in u


def test_admin_blocking_user_and_token_invalidation(client, db, signup, admin_headers):
    h_c, u_c = signup("customer", "+998901230007", "Bloklanuvchi Mijoz")

    # Avval token ishlaydi
    r_me = client.get("/api/v1/auth/me", headers=h_c)
    assert r_me.status_code == 200

    # Admin foydalanuvchini bloklaydi: PATCH /admin/users/{id}/status {is_active: false}
    r_block = client.patch(
        f"/api/v1/admin/users/{u_c['id']}/status",
        json={"is_active": False},
        headers=admin_headers,
    )
    assert r_block.status_code == 200
    assert r_block.json()["is_active"] is False

    # Bloklangan foydalanuvchining mavjud tokeni 401 beradi
    r_me_blocked = client.get("/api/v1/auth/me", headers=h_c)
    assert r_me_blocked.status_code == 401

    # Login qilishga urinish 403 beradi
    r_login = client.post(
        "/api/v1/auth/login",
        json={"phone": "+998901230007", "password": "secret123"},
    )
    assert r_login.status_code == 403

    # Foydalanuvchini qayta faollashtirish
    r_unblock = client.patch(
        f"/api/v1/admin/users/{u_c['id']}/status",
        json={"is_active": True},
        headers=admin_headers,
    )
    assert r_unblock.status_code == 200
    assert r_unblock.json()["is_active"] is True

    # Endi login 200 beradi
    r_login_ok = client.post(
        "/api/v1/auth/login",
        json={"phone": "+998901230007", "password": "secret123"},
    )
    assert r_login_ok.status_code == 200


def test_cannot_block_admin_or_self(client, db, make_admin, admin_headers):
    # O'zini bloklashga urinish -> 409
    admin = db.scalar(select(models.User).where(models.User.role == Role.ADMIN))
    r_self = client.patch(
        f"/api/v1/admin/users/{admin.id}/status",
        json={"is_active": False},
        headers=admin_headers,
    )
    assert r_self.status_code == 409

    # Boshqa adminni bloklashga urinish -> 409
    other_admin = make_admin(phone="+998900000009", password="admin99999", full_name="Admin 2")
    r_other = client.patch(
        f"/api/v1/admin/users/{other_admin.id}/status",
        json={"is_active": False},
        headers=admin_headers,
    )
    assert r_other.status_code == 409


def test_master_approval_toggle_visibility(client, db, signup, admin_headers, make_category):
    cat = make_category("Santexnik", "santexnik_appr_vis")
    h_m, u_m = signup("master", "+998901230008", "Yangi Usta Appr")
    mp = _create_master_profile(db, u_m["id"], cat.id, is_approved=False)

    # Dastlab unapproved -> GET /masters da ko'rinmaydi
    r_list1 = client.get(f"/api/v1/masters?category_id={cat.id}")
    assert not any(m["id"] == mp.id for m in r_list1.json())

    # Admin tasdiqlaydi: PATCH /admin/masters/{id}/approval {is_approved: true}
    r_app = client.patch(
        f"/api/v1/admin/masters/{mp.id}/approval",
        json={"is_approved": True},
        headers=admin_headers,
    )
    assert r_app.status_code == 200
    assert r_app.json()["is_approved"] is True

    # Endi GET /masters da ko'rinadi
    r_list2 = client.get(f"/api/v1/masters?category_id={cat.id}")
    assert any(m["id"] == mp.id for m in r_list2.json())

    # Admin bekor qiladi
    r_rev = client.patch(
        f"/api/v1/admin/masters/{mp.id}/approval",
        json={"is_approved": False},
        headers=admin_headers,
    )
    assert r_rev.status_code == 200
    assert r_rev.json()["is_approved"] is False

    # Yana ko'rinmaydi
    r_list3 = client.get(f"/api/v1/masters?category_id={cat.id}")
    assert not any(m["id"] == mp.id for m in r_list3.json())


def test_admin_assign_master_happy_path_and_errors(client, db, signup, admin_headers, make_category):
    cat = make_category("Santexnik", "santexnik_assign_api")
    cat2 = make_category("Elektrik", "elektrik_assign_api")
    h_c, u_c = signup("customer", "+998901230010", "Mijoz Assign")
    h_m, u_m = signup("master", "+998901230011", "Usta Assign")
    mp = _create_master_profile(db, u_m["id"], cat.id, is_approved=True, is_available=True)

    order_id = _create_order(client, h_c, cat.id)

    # Nomos usta (boshqa toifa) bilan biriktirishga urinish -> 409
    h_m2, u_m2 = signup("master", "+998901230012", "Elektrik Usta")
    mp_ineligible = _create_master_profile(db, u_m2["id"], cat2.id, is_approved=True)

    r_inel = client.patch(
        f"/api/v1/admin/orders/{order_id}/assign",
        json={"master_id": mp_ineligible.id},
        headers=admin_headers,
    )
    assert r_inel.status_code == 409

    # Muvaffaqiyatli biriktirish: PATCH /admin/orders/{id}/assign {master_id}
    r_assign = client.patch(
        f"/api/v1/admin/orders/{order_id}/assign",
        json={"master_id": mp.id},
        headers=admin_headers,
    )
    assert r_assign.status_code == 200, r_assign.text
    ord_data = r_assign.json()
    assert ord_data["status"] == "assigned"
    assert ord_data["master_id"] == mp.id

    # Tarixda admin qayd etilgan
    db.expire_all()
    hist = db.scalars(
        select(models.OrderStatusHistory).where(models.OrderStatusHistory.order_id == order_id)
    ).all()
    admin_user = db.scalar(select(models.User).where(models.User.role == Role.ADMIN))
    assert any(h.to_status == OrderStatus.ASSIGNED and h.changed_by == admin_user.id for h in hist)

    # Allaqachon biriktirilgan buyurtmaga ikkinchi urinish -> 409
    r_again = client.patch(
        f"/api/v1/admin/orders/{order_id}/assign",
        json={"master_id": mp.id},
        headers=admin_headers,
    )
    assert r_again.status_code == 409


def test_admin_commissions_totals_match_full_flow(client, db, signup, admin_headers, make_category):
    """Admin /admin/commissions hisoboti to'liq jarayon testidagi raqamlar bilan mos (200000 -> 20000)."""
    cat = make_category("Santexnik", "santexnik_comm_flow")
    h_c, u_c = signup("customer", "+998901230020", "Mijoz Comm")
    h_m, u_m = signup("master", "+998901230021", "Usta Comm")
    mp = _create_master_profile(db, u_m["id"], cat.id, pricing_type=PricingType.QUOTE, base_price=None)

    # 1. Buyurtma yaratamiz
    r_create = client.post(
        "/api/v1/orders",
        json={
            "category_id": cat.id,
            "description": "Quvurni ta'mirlash",
            "city": "Toshkent",
            "district": "Chilonzor",
            "address": "Muqimiy 45",
            "selection_mode": "manual",
        },
        headers=h_c,
    )
    assert r_create.status_code == 201
    order_id = r_create.json()["id"]

    # 2. Mijoz ustani tanlaydi
    client.post(f"/api/v1/orders/{order_id}/select-master", json={"master_id": mp.id}, headers=h_c)
    # 3. Usta qabul qiladi
    client.post(f"/api/v1/orders/{order_id}/accept", headers=h_m)
    # 4. Usta 200 000 taklif qiladi
    r_quote = client.post(
        f"/api/v1/orders/{order_id}/quotes",
        json={"price": 200_000, "note": "Kran bilan"},
        headers=h_m,
    )
    quote_id = r_quote.json()["id"]
    # 5. Mijoz narxni qabul qiladi
    client.post(f"/api/v1/orders/{order_id}/quotes/{quote_id}/accept", headers=h_c)
    # 6. Usta boshlaydi
    client.post(f"/api/v1/orders/{order_id}/start", headers=h_m)
    # 7. Usta yakunlaydi
    client.post(f"/api/v1/orders/{order_id}/complete", headers=h_m)

    # 8. Admin komissiya hisobotini oladi: GET /admin/commissions
    r_comm = client.get("/api/v1/admin/commissions", headers=admin_headers)
    assert r_comm.status_code == 200, r_comm.text
    comm = r_comm.json()
    assert comm["total_completed_orders"] >= 1
    assert comm["gross_total"] == 200_000
    assert comm["commission_total"] == 20_000

    order_item = next(o for o in comm["orders"] if o["id"] == order_id)
    assert order_item["agreed_price"] == 200_000
    assert order_item["commission_amount"] == 20_000
    assert order_item["master_net"] == 180_000
