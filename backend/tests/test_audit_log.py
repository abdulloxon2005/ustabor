"""Admin audit log: amallardan keyin yozuv yaratilishi, ro'yxat, filterlar, ruxsatlar."""

from app import models
from app.models.enums import OrderStatus, PricingType, Role
from app.core.security import create_access_token, hash_password

_PASSWORD_HASH = hash_password("secret123")

AUDIT_LOG = "/api/v1/admin/audit-log"


def _make_admin(db, auth_header, phone="+998901100001", full_name="Admin A"):
    admin = models.User(phone=phone, password_hash=_PASSWORD_HASH, full_name=full_name, role=Role.ADMIN)
    db.add(admin)
    db.commit()
    return admin, auth_header(create_access_token(admin.id))


def _make_customer(db, auth_header, phone="+998901100002"):
    customer = models.User(phone=phone, password_hash=_PASSWORD_HASH, full_name="Mijoz", role=Role.CUSTOMER)
    db.add(customer)
    db.commit()
    return customer, auth_header(create_access_token(customer.id))


def test_create_category_writes_audit_log(client, db, auth_header):
    admin, admin_headers = _make_admin(db, auth_header)
    r = client.post(
        "/api/v1/admin/categories",
        json={"name": "Elektrik"},
        headers=admin_headers,
    )
    assert r.status_code == 201, r.text
    category_id = r.json()["id"]

    entry = db.query(models.AdminAuditLog).filter_by(action="create_category").one()
    assert entry.admin_id == admin.id
    assert entry.target_type == "category"
    assert entry.target_id == category_id
    assert entry.detail == "Elektrik"


def test_update_category_writes_audit_log(client, db, auth_header):
    admin, admin_headers = _make_admin(db, auth_header)
    cat = models.Category(name="Santexnik", slug="santexnik", is_active=True)
    db.add(cat)
    db.commit()

    r = client.patch(
        f"/api/v1/admin/categories/{cat.id}",
        json={"name": "Santexnika"},
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text

    entry = db.query(models.AdminAuditLog).filter_by(action="update_category").one()
    assert entry.target_id == cat.id


def test_master_approval_writes_audit_log(client, db, auth_header):
    admin, admin_headers = _make_admin(db, auth_header)
    master_user = models.User(
        phone="+998901100003", password_hash=_PASSWORD_HASH, full_name="Usta A", role=Role.MASTER
    )
    db.add(master_user)
    db.flush()
    profile = models.MasterProfile(user_id=master_user.id, city="Toshkent", district="Chilonzor")
    db.add(profile)
    db.commit()

    r = client.patch(
        f"/api/v1/admin/masters/{profile.id}/approval",
        json={"is_approved": True},
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text

    entry = db.query(models.AdminAuditLog).filter_by(action="approve_master").one()
    assert entry.target_type == "master_profile"
    assert entry.target_id == profile.id

    r2 = client.patch(
        f"/api/v1/admin/masters/{profile.id}/approval",
        json={"is_approved": False},
        headers=admin_headers,
    )
    assert r2.status_code == 200
    entry2 = db.query(models.AdminAuditLog).filter_by(action="revoke_master_approval").one()
    assert entry2.target_id == profile.id


def test_assign_master_writes_audit_log(client, db, auth_header):
    admin, admin_headers = _make_admin(db, auth_header)
    cat = models.Category(name="Santexnik2", slug="santexnik2", is_active=True)
    db.add(cat)
    customer, _ = _make_customer(db, auth_header)
    master_user = models.User(
        phone="+998901100004", password_hash=_PASSWORD_HASH, full_name="Usta B", role=Role.MASTER
    )
    db.add(master_user)
    db.flush()
    profile = models.MasterProfile(
        user_id=master_user.id, city="Toshkent", district="Chilonzor", is_approved=True, is_available=True
    )
    db.add(profile)
    db.flush()
    db.add(
        models.MasterService(
            master_id=profile.id, category_id=cat.id, pricing_type=PricingType.QUOTE, base_price=None
        )
    )
    order = models.Order(
        customer_id=customer.id,
        category_id=cat.id,
        description="Elektr simlari",
        city="Toshkent",
        district="Chilonzor",
        address="2-uy",
        status=OrderStatus.SEARCHING,
        selection_mode="manual",
        commission_rate=10,
    )
    db.add(order)
    db.commit()

    r = client.patch(
        f"/api/v1/admin/orders/{order.id}/assign",
        json={"master_id": profile.id},
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text

    entry = db.query(models.AdminAuditLog).filter_by(action="assign_master").one()
    assert entry.target_type == "order"
    assert entry.target_id == order.id


def test_cancel_order_writes_audit_log(client, db, auth_header):
    admin, admin_headers = _make_admin(db, auth_header)
    cat = models.Category(name="Santexnik3", slug="santexnik3", is_active=True)
    db.add(cat)
    customer, _ = _make_customer(db, auth_header, phone="+998901100005")
    db.flush()
    order = models.Order(
        customer_id=customer.id,
        category_id=cat.id,
        description="Nasos ishlamayapti",
        city="Toshkent",
        district="Chilonzor",
        address="3-uy",
        status=OrderStatus.SEARCHING,
        selection_mode="manual",
        commission_rate=10,
    )
    db.add(order)
    db.commit()

    r = client.post(f"/api/v1/admin/orders/{order.id}/cancel", headers=admin_headers)
    assert r.status_code == 200, r.text

    entry = db.query(models.AdminAuditLog).filter_by(action="cancel_order").one()
    assert entry.target_id == order.id


def test_block_and_unblock_user_writes_audit_log(client, db, auth_header):
    admin, admin_headers = _make_admin(db, auth_header)
    customer, _ = _make_customer(db, auth_header, phone="+998901100006")

    r = client.patch(
        f"/api/v1/admin/users/{customer.id}/status",
        json={"is_active": False},
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    entry = db.query(models.AdminAuditLog).filter_by(action="block_user").one()
    assert entry.target_type == "user"
    assert entry.target_id == customer.id

    r2 = client.patch(
        f"/api/v1/admin/users/{customer.id}/status",
        json={"is_active": True},
        headers=admin_headers,
    )
    assert r2.status_code == 200
    entry2 = db.query(models.AdminAuditLog).filter_by(action="unblock_user").one()
    assert entry2.target_id == customer.id


def test_resolve_dispute_writes_audit_log(client, db, auth_header):
    admin, admin_headers = _make_admin(db, auth_header)
    cat = models.Category(name="Santexnik4", slug="santexnik4", is_active=True)
    db.add(cat)
    customer, customer_headers = _make_customer(db, auth_header, phone="+998901100007")
    db.flush()
    order = models.Order(
        customer_id=customer.id,
        category_id=cat.id,
        description="Muammo",
        city="Toshkent",
        district="Chilonzor",
        address="4-uy",
        status=OrderStatus.COMPLETED,
        selection_mode="manual",
        agreed_price=100_000,
        commission_rate=10,
    )
    db.add(order)
    db.commit()

    r_create = client.post(
        f"/api/v1/orders/{order.id}/dispute",
        json={"reason": "Ish sifatsiz bajarildi"},
        headers=customer_headers,
    )
    dispute_id = r_create.json()["id"]

    r = client.patch(
        f"/api/v1/admin/disputes/{dispute_id}",
        json={"status": "resolved"},
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text

    entry = db.query(models.AdminAuditLog).filter_by(action="resolve_dispute").one()
    assert entry.target_type == "dispute"
    assert entry.target_id == dispute_id
    assert entry.detail == "resolved"


def test_list_audit_log_returns_items_with_admin_name(client, db, auth_header):
    admin, admin_headers = _make_admin(db, auth_header, phone="+998901100008", full_name="Bosh Admin")
    client.post("/api/v1/admin/categories", json={"name": "Duradgor"}, headers=admin_headers)

    r = client.get(AUDIT_LOG, headers=admin_headers)
    assert r.status_code == 200, r.text
    items = r.json()
    assert len(items) == 1
    assert items[0]["action"] == "create_category"
    assert items[0]["admin_name"] == "Bosh Admin"
    assert items[0]["admin_id"] == admin.id


def test_list_audit_log_filters_by_admin_and_action(client, db, auth_header):
    admin1, admin1_headers = _make_admin(db, auth_header, phone="+998901100009", full_name="Admin Bir")
    admin2, admin2_headers = _make_admin(db, auth_header, phone="+998901100010", full_name="Admin Ikki")

    client.post("/api/v1/admin/categories", json={"name": "Payshanba"}, headers=admin1_headers)
    client.post("/api/v1/admin/categories", json={"name": "Juma"}, headers=admin2_headers)

    r_all = client.get(AUDIT_LOG, headers=admin1_headers)
    assert len(r_all.json()) == 2

    r_by_admin = client.get(f"{AUDIT_LOG}?admin_id={admin1.id}", headers=admin1_headers)
    items = r_by_admin.json()
    assert len(items) == 1
    assert items[0]["admin_id"] == admin1.id

    r_by_action = client.get(f"{AUDIT_LOG}?action=create_category", headers=admin1_headers)
    assert len(r_by_action.json()) == 2

    r_by_action_none = client.get(f"{AUDIT_LOG}?action=cancel_order", headers=admin1_headers)
    assert len(r_by_action_none.json()) == 0


def test_audit_log_requires_admin(client, db, auth_header):
    _, customer_headers = _make_customer(db, auth_header, phone="+998901100011")
    r = client.get(AUDIT_LOG, headers=customer_headers)
    assert r.status_code == 403

    r_anon = client.get(AUDIT_LOG)
    assert r_anon.status_code == 401
