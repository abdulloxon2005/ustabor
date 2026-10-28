"""Chat (buyurtma ichidagi xabarlashish): ruxsatlar va asosiy oqim."""

from app import models
from app.models.enums import OfferStatus, OrderStatus, PricingType, QuoteStatus, Role
from app.core.security import create_access_token, hash_password

_PASSWORD_HASH = hash_password("secret123")

MESSAGES = "/api/v1/orders/{id}/messages"


def _build_env(db, auth_header):
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
    other_master_user = models.User(
        phone="+998901000004", password_hash=_PASSWORD_HASH, full_name="Usta B", role=Role.MASTER
    )
    admin = models.User(
        phone="+998901000005", password_hash=_PASSWORD_HASH, full_name="Admin", role=Role.ADMIN
    )
    db.add_all([customer, other_customer, master_user, other_master_user, admin])
    db.flush()

    master_profile = models.MasterProfile(
        user_id=master_user.id, city="Toshkent", district="Chilonzor", is_approved=True, is_available=True
    )
    other_master_profile = models.MasterProfile(
        user_id=other_master_user.id, city="Toshkent", district="Chilonzor", is_approved=True, is_available=True
    )
    db.add_all([master_profile, other_master_profile])
    db.flush()

    db.add(
        models.MasterService(
            master_id=master_profile.id, category_id=cat.id, pricing_type=PricingType.QUOTE, base_price=None
        )
    )

    order_assigned = models.Order(
        customer_id=customer.id,
        category_id=cat.id,
        master_id=master_profile.id,
        description="Kran suv oqizyapti",
        city="Toshkent",
        district="Chilonzor",
        address="1-uy",
        status=OrderStatus.ASSIGNED,
        selection_mode="manual",
        commission_rate=10,
    )
    order_searching = models.Order(
        customer_id=customer.id,
        category_id=cat.id,
        master_id=None,
        description="Rozetka ishlamayapti",
        city="Toshkent",
        district="Chilonzor",
        address="2-uy",
        status=OrderStatus.SEARCHING,
        selection_mode="manual",
        commission_rate=10,
    )
    db.add_all([order_assigned, order_searching])
    db.commit()

    return {
        "order_assigned_id": order_assigned.id,
        "order_searching_id": order_searching.id,
        "customer_headers": auth_header(create_access_token(customer.id)),
        "other_customer_headers": auth_header(create_access_token(other_customer.id)),
        "master_headers": auth_header(create_access_token(master_user.id)),
        "other_master_headers": auth_header(create_access_token(other_master_user.id)),
        "admin_headers": auth_header(create_access_token(admin.id)),
    }


def test_customer_and_master_can_chat(client, db, auth_header):
    env = _build_env(db, auth_header)
    oid = env["order_assigned_id"]

    r1 = client.post(
        MESSAGES.format(id=oid), json={"body": "Qachon kelasiz?"}, headers=env["customer_headers"]
    )
    assert r1.status_code == 201, r1.text
    assert r1.json()["sender_name"] == "Mijoz A"

    r2 = client.post(
        MESSAGES.format(id=oid), json={"body": "Ertaga soat 10 da"}, headers=env["master_headers"]
    )
    assert r2.status_code == 201, r2.text

    r_list_customer = client.get(MESSAGES.format(id=oid), headers=env["customer_headers"])
    assert r_list_customer.status_code == 200
    bodies = [m["body"] for m in r_list_customer.json()]
    assert bodies == ["Qachon kelasiz?", "Ertaga soat 10 da"]

    r_list_master = client.get(MESSAGES.format(id=oid), headers=env["master_headers"])
    assert [m["body"] for m in r_list_master.json()] == bodies


def test_admin_can_read_but_not_write(client, db, auth_header):
    env = _build_env(db, auth_header)
    oid = env["order_assigned_id"]
    client.post(MESSAGES.format(id=oid), json={"body": "Salom"}, headers=env["customer_headers"])

    r_read = client.get(MESSAGES.format(id=oid), headers=env["admin_headers"])
    assert r_read.status_code == 200
    assert len(r_read.json()) == 1

    r_write = client.post(
        MESSAGES.format(id=oid), json={"body": "Admin yozyapti"}, headers=env["admin_headers"]
    )
    assert r_write.status_code == 403


def test_other_customer_cannot_access(client, db, auth_header):
    env = _build_env(db, auth_header)
    oid = env["order_assigned_id"]

    r_get = client.get(MESSAGES.format(id=oid), headers=env["other_customer_headers"])
    assert r_get.status_code == 404

    r_post = client.post(
        MESSAGES.format(id=oid), json={"body": "Men kira olamanmi?"}, headers=env["other_customer_headers"]
    )
    assert r_post.status_code == 404


def test_unrelated_master_cannot_access(client, db, auth_header):
    env = _build_env(db, auth_header)
    oid = env["order_assigned_id"]

    r_get = client.get(MESSAGES.format(id=oid), headers=env["other_master_headers"])
    assert r_get.status_code == 404

    r_post = client.post(
        MESSAGES.format(id=oid), json={"body": "Salom"}, headers=env["other_master_headers"]
    )
    assert r_post.status_code == 404


def test_cannot_message_order_without_master(client, db, auth_header):
    env = _build_env(db, auth_header)
    oid = env["order_searching_id"]

    r = client.post(
        MESSAGES.format(id=oid), json={"body": "Hali hech kim yo'q"}, headers=env["customer_headers"]
    )
    assert r.status_code == 409


def test_empty_message_rejected(client, db, auth_header):
    env = _build_env(db, auth_header)
    oid = env["order_assigned_id"]

    r = client.post(MESSAGES.format(id=oid), json={"body": "   "}, headers=env["customer_headers"])
    assert r.status_code == 422


def test_messages_require_auth(client, db, auth_header):
    env = _build_env(db, auth_header)
    oid = env["order_assigned_id"]
    assert client.get(MESSAGES.format(id=oid)).status_code == 401
    assert client.post(MESSAGES.format(id=oid), json={"body": "x"}).status_code == 401
