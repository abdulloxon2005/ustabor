"""Shikoyat/nizo tizimi: yaratish, ruxsatlar, admin hal qilishi."""

from app import models
from app.models.enums import OrderStatus, PricingType, Role
from app.core.security import create_access_token, hash_password

_PASSWORD_HASH = hash_password("secret123")

DISPUTES = "/api/v1/orders/{id}/disputes"
DISPUTE = "/api/v1/orders/{id}/dispute"
ADMIN_DISPUTES = "/api/v1/admin/disputes"


def _build_env(db, auth_header, order_status=OrderStatus.COMPLETED, with_master=True):
    cat = models.Category(name="Santexnik", slug="santexnik", is_active=True)
    db.add(cat)

    customer = models.User(
        phone="+998901000001", password_hash=_PASSWORD_HASH, full_name="Mijoz A", role=Role.CUSTOMER
    )
    other_customer = models.User(
        phone="+998901000002", password_hash=_PASSWORD_HASH, full_name="Mijoz B", role=Role.CUSTOMER
    )
    master_user = models.User(
        phone="+998901000003", password_hash=_PASSWORD_HASH, full_name="Usta A", role=Role.MASTER
    )
    admin = models.User(
        phone="+998901000005", password_hash=_PASSWORD_HASH, full_name="Admin", role=Role.ADMIN
    )
    db.add_all([customer, other_customer, master_user, admin])
    db.flush()

    master_profile = None
    master_id = None
    if with_master:
        master_profile = models.MasterProfile(
            user_id=master_user.id, city="Toshkent", district="Chilonzor", is_approved=True, is_available=True
        )
        db.add(master_profile)
        db.flush()
        db.add(
            models.MasterService(
                master_id=master_profile.id, category_id=cat.id, pricing_type=PricingType.QUOTE, base_price=None
            )
        )
        master_id = master_profile.id

    order = models.Order(
        customer_id=customer.id,
        category_id=cat.id,
        master_id=master_id,
        description="Kran suv oqizyapti",
        city="Toshkent",
        district="Chilonzor",
        address="1-uy",
        status=order_status,
        selection_mode="manual",
        agreed_price=150_000 if master_id else None,
        commission_rate=10,
    )
    db.add(order)
    db.commit()

    return {
        "order_id": order.id,
        "customer_headers": auth_header(create_access_token(customer.id)),
        "other_customer_headers": auth_header(create_access_token(other_customer.id)),
        "master_headers": auth_header(create_access_token(master_user.id)),
        "admin_headers": auth_header(create_access_token(admin.id)),
    }


def test_customer_can_raise_dispute_on_completed_order(client, db, auth_header):
    env = _build_env(db, auth_header, order_status=OrderStatus.COMPLETED)
    r = client.post(
        DISPUTE.format(id=env["order_id"]),
        json={"reason": "Ish sifatsiz bajarildi"},
        headers=env["customer_headers"],
    )
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "open"
    assert r.json()["reason"] == "Ish sifatsiz bajarildi"


def test_master_can_raise_dispute(client, db, auth_header):
    env = _build_env(db, auth_header, order_status=OrderStatus.IN_PROGRESS)
    r = client.post(
        DISPUTE.format(id=env["order_id"]),
        json={"reason": "Mijoz to'lovni rad etdi"},
        headers=env["master_headers"],
    )
    assert r.status_code == 201, r.text


def test_dispute_requires_appropriate_status(client, db, auth_header):
    env = _build_env(db, auth_header, order_status=OrderStatus.SEARCHING, with_master=False)
    r = client.post(
        DISPUTE.format(id=env["order_id"]),
        json={"reason": "Hali boshlanmagan"},
        headers=env["customer_headers"],
    )
    assert r.status_code == 409


def test_dispute_allowed_for_cancelled_order(client, db, auth_header):
    env = _build_env(db, auth_header, order_status=OrderStatus.CANCELLED)
    r = client.post(
        DISPUTE.format(id=env["order_id"]),
        json={"reason": "Bekor qilingan, lekin muammo bor"},
        headers=env["customer_headers"],
    )
    assert r.status_code == 201


def test_cannot_open_second_dispute_while_one_open(client, db, auth_header):
    env = _build_env(db, auth_header, order_status=OrderStatus.COMPLETED)
    r1 = client.post(
        DISPUTE.format(id=env["order_id"]),
        json={"reason": "Birinchi shikoyat"},
        headers=env["customer_headers"],
    )
    assert r1.status_code == 201

    r2 = client.post(
        DISPUTE.format(id=env["order_id"]),
        json={"reason": "Ikkinchi shikoyat"},
        headers=env["customer_headers"],
    )
    assert r2.status_code == 409


def test_other_customer_cannot_raise_dispute(client, db, auth_header):
    env = _build_env(db, auth_header, order_status=OrderStatus.COMPLETED)
    r = client.post(
        DISPUTE.format(id=env["order_id"]),
        json={"reason": "Men aloqador emasman"},
        headers=env["other_customer_headers"],
    )
    assert r.status_code == 404


def test_admin_cannot_raise_dispute(client, db, auth_header):
    env = _build_env(db, auth_header, order_status=OrderStatus.COMPLETED)
    r = client.post(
        DISPUTE.format(id=env["order_id"]),
        json={"reason": "Admin nomidan"},
        headers=env["admin_headers"],
    )
    assert r.status_code == 403


def test_reason_too_short_rejected(client, db, auth_header):
    env = _build_env(db, auth_header, order_status=OrderStatus.COMPLETED)
    r = client.post(
        DISPUTE.format(id=env["order_id"]),
        json={"reason": "qisqa"[:3]},
        headers=env["customer_headers"],
    )
    assert r.status_code == 422


def test_list_order_disputes_visible_to_participants_and_admin(client, db, auth_header):
    env = _build_env(db, auth_header, order_status=OrderStatus.COMPLETED)
    client.post(
        DISPUTE.format(id=env["order_id"]),
        json={"reason": "Muammo bor"},
        headers=env["customer_headers"],
    )

    for key in ("customer_headers", "master_headers", "admin_headers"):
        r = client.get(DISPUTES.format(id=env["order_id"]), headers=env[key])
        assert r.status_code == 200, key
        assert len(r.json()) == 1

    r_other = client.get(DISPUTES.format(id=env["order_id"]), headers=env["other_customer_headers"])
    assert r_other.status_code == 404


def test_admin_resolve_dispute(client, db, auth_header):
    env = _build_env(db, auth_header, order_status=OrderStatus.COMPLETED)
    r_create = client.post(
        DISPUTE.format(id=env["order_id"]),
        json={"reason": "Ish sifatsiz"},
        headers=env["customer_headers"],
    )
    dispute_id = r_create.json()["id"]

    r_resolve = client.patch(
        f"/api/v1/admin/disputes/{dispute_id}",
        json={"status": "resolved", "admin_note": "Ustaga ogohlantirish berildi"},
        headers=env["admin_headers"],
    )
    assert r_resolve.status_code == 200, r_resolve.text
    body = r_resolve.json()
    assert body["status"] == "resolved"
    assert body["admin_note"] == "Ustaga ogohlantirish berildi"
    assert body["resolved_at"] is not None


def test_admin_reject_dispute(client, db, auth_header):
    env = _build_env(db, auth_header, order_status=OrderStatus.COMPLETED)
    r_create = client.post(
        DISPUTE.format(id=env["order_id"]),
        json={"reason": "Noto'g'ri ayb"},
        headers=env["customer_headers"],
    )
    dispute_id = r_create.json()["id"]

    r_resolve = client.patch(
        f"/api/v1/admin/disputes/{dispute_id}",
        json={"status": "rejected"},
        headers=env["admin_headers"],
    )
    assert r_resolve.status_code == 200
    assert r_resolve.json()["status"] == "rejected"


def test_cannot_resolve_already_resolved_dispute(client, db, auth_header):
    env = _build_env(db, auth_header, order_status=OrderStatus.COMPLETED)
    r_create = client.post(
        DISPUTE.format(id=env["order_id"]),
        json={"reason": "Masala"},
        headers=env["customer_headers"],
    )
    dispute_id = r_create.json()["id"]
    client.patch(
        f"/api/v1/admin/disputes/{dispute_id}",
        json={"status": "resolved"},
        headers=env["admin_headers"],
    )

    r2 = client.patch(
        f"/api/v1/admin/disputes/{dispute_id}",
        json={"status": "rejected"},
        headers=env["admin_headers"],
    )
    assert r2.status_code == 409


def test_non_admin_cannot_resolve_dispute(client, db, auth_header):
    env = _build_env(db, auth_header, order_status=OrderStatus.COMPLETED)
    r_create = client.post(
        DISPUTE.format(id=env["order_id"]),
        json={"reason": "Masala"},
        headers=env["customer_headers"],
    )
    dispute_id = r_create.json()["id"]

    r = client.patch(
        f"/api/v1/admin/disputes/{dispute_id}",
        json={"status": "resolved"},
        headers=env["customer_headers"],
    )
    assert r.status_code == 403


def test_admin_list_disputes_and_filter_by_status(client, db, auth_header):
    env1 = _build_env(db, auth_header, order_status=OrderStatus.COMPLETED)
    client.post(
        DISPUTE.format(id=env1["order_id"]),
        json={"reason": "Birinchi muammo"},
        headers=env1["customer_headers"],
    )

    r_list = client.get(ADMIN_DISPUTES, headers=env1["admin_headers"])
    assert r_list.status_code == 200
    items = r_list.json()
    assert len(items) == 1
    assert items[0]["raised_by_name"] == "Mijoz A"
    assert items[0]["raised_by_role"] == "customer"
    assert items[0]["category_name"] == "Santexnik"

    r_open = client.get(ADMIN_DISPUTES + "?status=open", headers=env1["admin_headers"])
    assert len(r_open.json()) == 1

    r_resolved = client.get(ADMIN_DISPUTES + "?status=resolved", headers=env1["admin_headers"])
    assert len(r_resolved.json()) == 0


def test_disputes_require_auth(client, db, auth_header):
    env = _build_env(db, auth_header, order_status=OrderStatus.COMPLETED)
    assert client.get(DISPUTES.format(id=env["order_id"])).status_code == 401
    assert client.post(DISPUTE.format(id=env["order_id"]), json={"reason": "x"}).status_code == 401


def test_my_disputes_customer_and_master_and_admin_notification(client, db, auth_header):
    env = _build_env(db, auth_header, order_status=OrderStatus.ASSIGNED)
    # 1. Customer raises complaint via /orders/my-disputes with order_id
    r_cust = client.post(
        "/api/v1/orders/my-disputes",
        json={"order_id": env["order_id"], "reason": "Usta qo'ng'iroqqa javob bermayapti"},
        headers=env["customer_headers"],
    )
    assert r_cust.status_code == 201, r_cust.text

    # 2. Master raises general complaint via /orders/my-disputes without order_id
    r_master = client.post(
        "/api/v1/orders/my-disputes",
        json={"reason": "Ilovada buyurtma manzili noto'g'ri chiqyapti"},
        headers=env["master_headers"],
    )
    assert r_master.status_code == 201, r_master.text
    assert r_master.json()["order_id"] is None

    # 3. Customer sees own complaint in /orders/my-disputes
    r_cust_list = client.get("/api/v1/orders/my-disputes", headers=env["customer_headers"])
    assert r_cust_list.status_code == 200
    assert len(r_cust_list.json()) == 1
    assert r_cust_list.json()[0]["order_id"] == env["order_id"]

    # 4. Master sees own complaint in /orders/my-disputes
    r_master_list = client.get("/api/v1/orders/my-disputes", headers=env["master_headers"])
    assert r_master_list.status_code == 200
    assert len(r_master_list.json()) == 1
    assert r_master_list.json()[0]["category_name"] == "Umumiy shikoyat"

    # 5. Admin sees both complaints in /admin/disputes and receives notifications
    r_admin = client.get(ADMIN_DISPUTES, headers=env["admin_headers"])
    assert r_admin.status_code == 200
    assert len(r_admin.json()) == 2

    r_notif = client.get("/api/v1/notifications", headers=env["admin_headers"])
    assert r_notif.status_code == 200
    dispute_notifs = [n for n in r_notif.json() if n["type"] == "new_dispute"]
    assert len(dispute_notifs) >= 2

