"""Bildirishnoma: hook nuqtalari (new_offer, order_assigned, quote_accepted,
order_completed, master_approved) va /notifications endpointlari."""

from app import models
from app.models.enums import PricingType, Role
from app.services import sms

NOTIFICATIONS = "/api/v1/notifications"


def _quotes_master_setup(db, auth_header, make_category):
    """Mijoz, usta (quote turidagi xizmat bilan, tasdiqlangan) va kategoriya yaratadi."""
    cat = make_category()

    customer = models.User(
        phone="+998901110000",
        password_hash="x",
        full_name="Mijoz",
        role=Role.CUSTOMER,
    )
    master_user = models.User(
        phone="+998902220000",
        password_hash="x",
        full_name="Usta",
        role=Role.MASTER,
    )
    db.add_all([customer, master_user])
    db.flush()

    master_profile = models.MasterProfile(
        user_id=master_user.id,
        city="Toshkent",
        district="Chilonzor",
        is_approved=True,
        is_available=True,
    )
    db.add(master_profile)
    db.flush()

    db.add(
        models.MasterService(
            master_id=master_profile.id,
            category_id=cat.id,
            pricing_type=PricingType.QUOTE,
            base_price=None,
        )
    )
    db.commit()

    from app.core.security import create_access_token

    return {
        "cat": cat,
        "customer": customer,
        "master_user": master_user,
        "master_profile": master_profile,
        "customer_headers": auth_header(create_access_token(customer.id)),
        "master_headers": auth_header(create_access_token(master_user.id)),
    }


def _create_order(client, headers, cat_id, selection_mode="manual"):
    r = client.post(
        "/api/v1/orders",
        json={
            "category_id": cat_id,
            "description": "Kran suv oqizyapti, almashtirish kerak",
            "city": "Toshkent",
            "district": "Chilonzor",
            "address": "1-uy",
            "selection_mode": selection_mode,
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_new_offer_notifies_master(client, db, auth_header, make_category):
    env = _quotes_master_setup(db, auth_header, make_category)
    order = _create_order(client, env["customer_headers"], env["cat"].id)

    r = client.post(
        f"/api/v1/orders/{order['id']}/select-master",
        json={"master_id": env["master_profile"].id},
        headers=env["customer_headers"],
    )
    assert r.status_code == 200, r.text

    r_list = client.get(NOTIFICATIONS, headers=env["master_headers"])
    assert r_list.status_code == 200
    items = r_list.json()
    new_offer = next(n for n in items if n["type"] == "new_offer")
    # Usta bildirishnomada xizmat turi, mijoz ismi va shahar/tumanni ko'rishi kerak
    assert env["cat"].name in new_offer["body"]
    assert "Mijoz" in new_offer["body"]
    assert "Toshkent" in new_offer["body"]
    assert "Chilonzor" in new_offer["body"]

    assert sms.last_message_for(env["master_user"].phone) is not None


def test_order_assigned_notifies_customer(client, db, auth_header, make_category):
    env = _quotes_master_setup(db, auth_header, make_category)
    order = _create_order(client, env["customer_headers"], env["cat"].id)
    client.post(
        f"/api/v1/orders/{order['id']}/select-master",
        json={"master_id": env["master_profile"].id},
        headers=env["customer_headers"],
    )

    r_accept = client.post(
        f"/api/v1/orders/{order['id']}/accept", headers=env["master_headers"]
    )
    assert r_accept.status_code == 200, r_accept.text

    r_list = client.get(NOTIFICATIONS, headers=env["customer_headers"])
    types = [n["type"] for n in r_list.json()]
    assert "order_assigned" in types


def test_quote_accepted_notifies_master(client, db, auth_header, make_category):
    env = _quotes_master_setup(db, auth_header, make_category)
    order = _create_order(client, env["customer_headers"], env["cat"].id)
    client.post(
        f"/api/v1/orders/{order['id']}/select-master",
        json={"master_id": env["master_profile"].id},
        headers=env["customer_headers"],
    )
    client.post(f"/api/v1/orders/{order['id']}/accept", headers=env["master_headers"])

    r_quote = client.post(
        f"/api/v1/orders/{order['id']}/quotes",
        json={"price": 150000, "note": "Narx"},
        headers=env["master_headers"],
    )
    assert r_quote.status_code == 201, r_quote.text
    quote_id = r_quote.json()["id"]

    r_accept_quote = client.post(
        f"/api/v1/orders/{order['id']}/quotes/{quote_id}/accept",
        headers=env["customer_headers"],
    )
    assert r_accept_quote.status_code == 200, r_accept_quote.text

    r_list = client.get(NOTIFICATIONS, headers=env["master_headers"])
    types = [n["type"] for n in r_list.json()]
    assert "quote_accepted" in types


def test_order_completed_notifies_customer(client, db, auth_header, make_category):
    env = _quotes_master_setup(db, auth_header, make_category)
    order = _create_order(client, env["customer_headers"], env["cat"].id)
    client.post(
        f"/api/v1/orders/{order['id']}/select-master",
        json={"master_id": env["master_profile"].id},
        headers=env["customer_headers"],
    )
    client.post(f"/api/v1/orders/{order['id']}/accept", headers=env["master_headers"])
    r_quote = client.post(
        f"/api/v1/orders/{order['id']}/quotes",
        json={"price": 150000, "note": "Narx"},
        headers=env["master_headers"],
    )
    quote_id = r_quote.json()["id"]
    client.post(
        f"/api/v1/orders/{order['id']}/quotes/{quote_id}/accept",
        headers=env["customer_headers"],
    )
    client.post(f"/api/v1/orders/{order['id']}/start", headers=env["master_headers"])
    r_complete = client.post(
        f"/api/v1/orders/{order['id']}/complete", headers=env["master_headers"]
    )
    assert r_complete.status_code == 200, r_complete.text

    r_list = client.get(NOTIFICATIONS, headers=env["customer_headers"])
    types = [n["type"] for n in r_list.json()]
    assert "order_completed" in types


def test_master_approved_notifies_master(client, db, auth_header, make_admin):
    master_user = models.User(
        phone="+998903330000",
        password_hash="x",
        full_name="Yangi Usta",
        role=Role.MASTER,
    )
    db.add(master_user)
    db.flush()
    profile = models.MasterProfile(
        user_id=master_user.id, city="Toshkent", district="Chilonzor", is_approved=False
    )
    db.add(profile)
    db.commit()

    make_admin()
    r_admin_login = client.post(
        "/api/v1/auth/login", json={"phone": "+998900000000", "password": "admin12345"}
    )
    admin_headers = auth_header(r_admin_login.json()["access_token"])

    r = client.patch(
        f"/api/v1/admin/masters/{profile.id}/approval",
        json={"is_approved": True},
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text

    from app.core.security import create_access_token

    master_headers = auth_header(create_access_token(master_user.id))
    r_list = client.get(NOTIFICATIONS, headers=master_headers)
    types = [n["type"] for n in r_list.json()]
    assert "master_approved" in types


# ---------- endpointlar: ro'yxat, unread-count, read, read-all ----------


def test_unread_count_and_mark_read(client, db, auth_header, make_category):
    env = _quotes_master_setup(db, auth_header, make_category)
    order = _create_order(client, env["customer_headers"], env["cat"].id)
    client.post(
        f"/api/v1/orders/{order['id']}/select-master",
        json={"master_id": env["master_profile"].id},
        headers=env["customer_headers"],
    )

    r_count = client.get(f"{NOTIFICATIONS}/unread-count", headers=env["master_headers"])
    assert r_count.status_code == 200
    assert r_count.json()["unread_count"] == 1

    notif_id = client.get(NOTIFICATIONS, headers=env["master_headers"]).json()[0]["id"]
    r_read = client.post(f"{NOTIFICATIONS}/{notif_id}/read", headers=env["master_headers"])
    assert r_read.status_code == 200
    assert r_read.json()["is_read"] is True

    r_count2 = client.get(f"{NOTIFICATIONS}/unread-count", headers=env["master_headers"])
    assert r_count2.json()["unread_count"] == 0


def test_mark_all_read(client, db, auth_header, make_category):
    env = _quotes_master_setup(db, auth_header, make_category)
    for _ in range(2):
        order = _create_order(client, env["customer_headers"], env["cat"].id)
        client.post(
            f"/api/v1/orders/{order['id']}/select-master",
            json={"master_id": env["master_profile"].id},
            headers=env["customer_headers"],
        )
        client.post(f"/api/v1/orders/{order['id']}/reject", headers=env["master_headers"])

    r = client.post(f"{NOTIFICATIONS}/read-all", headers=env["master_headers"])
    assert r.status_code == 200

    r_count = client.get(f"{NOTIFICATIONS}/unread-count", headers=env["master_headers"])
    assert r_count.json()["unread_count"] == 0


def test_cannot_read_other_users_notification(client, db, auth_header, make_category):
    env = _quotes_master_setup(db, auth_header, make_category)
    order = _create_order(client, env["customer_headers"], env["cat"].id)
    client.post(
        f"/api/v1/orders/{order['id']}/select-master",
        json={"master_id": env["master_profile"].id},
        headers=env["customer_headers"],
    )
    notif_id = client.get(NOTIFICATIONS, headers=env["master_headers"]).json()[0]["id"]

    r = client.post(f"{NOTIFICATIONS}/{notif_id}/read", headers=env["customer_headers"])
    assert r.status_code == 404


def test_notifications_require_auth(client):
    assert client.get(NOTIFICATIONS).status_code == 401
    assert client.get(f"{NOTIFICATIONS}/unread-count").status_code == 401
