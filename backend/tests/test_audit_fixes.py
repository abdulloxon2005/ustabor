"""Kod auditida topilgan kamchiliklar uchun regressiya testlari."""

from app import models
from app.models.enums import OrderStatus, PricingType
from app.services import matching, sms
from app.services.notify import SMS_NOTIFICATION_TYPES

ORDERS = "/api/v1/orders"
MASTERS = "/api/v1/masters"


def _master(db, signup, phone, name, *, bio="", lat=None, lon=None, categories=()):
    headers, user = signup("master", phone, name)
    mp = models.MasterProfile(
        user_id=user["id"],
        bio=bio,
        city="Toshkent",
        district="Chilonzor",
        is_approved=True,
        is_available=True,
        rating_avg=4.5,
        rating_count=10,
        latitude=lat,
        longitude=lon,
        location_sharing_enabled=lat is not None,
    )
    db.add(mp)
    db.commit()
    db.refresh(mp)
    for cat in categories:
        db.add(models.MasterService(
            master_id=mp.id, category_id=cat.id,
            pricing_type=PricingType.FIXED, base_price=100_000,
        ))
    db.commit()
    return headers, mp


def _order(client, headers, cat_id, mode="manual"):
    r = client.post(ORDERS, json={
        "category_id": cat_id, "description": "Quvur ta'mirlash kerak",
        "city": "Toshkent", "district": "Chilonzor", "address": "Chilonzor 5",
        "selection_mode": mode,
    }, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def test_scoring_weights_sum_to_one():
    from app.core.config import settings
    total = (settings.MATCH_W_RATING + settings.MATCH_W_DISTRICT
             + settings.MATCH_W_NEW_BONUS + settings.MATCH_W_DISTANCE)
    assert abs(total - 1.0) < 1e-9


def test_list_masters_pagination(client, db, signup, make_category):
    cat = make_category("Santexnik", "santexnik")
    for i in range(3):
        _master(db, signup, f"+99890100000{i}", f"Usta {i}", categories=[cat])
    assert len(client.get(MASTERS).json()) == 3
    assert len(client.get(MASTERS, params={"limit": 2}).json()) == 2
    assert len(client.get(MASTERS, params={"limit": 2, "offset": 2}).json()) == 1
    assert client.get(MASTERS, params={"limit": 9999}).status_code == 200


def test_list_masters_search_matches_bio_and_category(client, db, signup, make_category):
    plumber = make_category("Santexnik", "santexnik")
    electric = make_category("Elektrik", "elektrik")
    _master(db, signup, "+998901000001", "Aziz", bio="Quvur va kran", categories=[plumber])
    _master(db, signup, "+998901000002", "Bobur", categories=[electric])

    by_name = client.get(MASTERS, params={"q": "aziz"}).json()
    assert [m["full_name"] for m in by_name] == ["Aziz"]
    by_bio = client.get(MASTERS, params={"q": "kran"}).json()
    assert [m["full_name"] for m in by_bio] == ["Aziz"]
    by_category = client.get(MASTERS, params={"q": "elektrik"}).json()
    assert [m["full_name"] for m in by_category] == ["Bobur"]


def test_nearby_uses_bounding_box_and_exact_distance(client, db, signup, make_category):
    cat = make_category("Santexnik", "santexnik")
    _master(db, signup, "+998901000001", "Yaqin", lat=41.311, lon=69.279, categories=[cat])
    _master(db, signup, "+998901000002", "Uzoq", lat=39.654, lon=66.975, categories=[cat])
    headers, _ = signup("customer", "+998909990000", "Mijoz")

    r = client.get(f"{MASTERS}/nearby", headers=headers,
                   params={"latitude": 41.3, "longitude": 69.28, "radius_km": 25})
    assert r.status_code == 200
    assert [m["full_name"] for m in r.json()] == ["Yaqin"]

    r = client.get(f"{MASTERS}/nearby", headers=headers,
                   params={"latitude": 41.3, "longitude": 69.28, "radius_km": 500})
    assert {m["full_name"] for m in r.json()} == {"Yaqin", "Uzoq"}


def test_cancel_assigned_order_notifies_master(client, db, signup, make_category):
    cat = make_category("Santexnik", "santexnik")
    cust_h, _ = signup("customer", "+998901112233", "Mijoz")
    master_h, mp = _master(db, signup, "+998902223344", "Usta", categories=[cat])
    order = _order(client, cust_h, cat.id)
    assert client.post(f"{ORDERS}/{order['id']}/select-master",
                       json={"master_id": mp.id}, headers=cust_h).status_code == 200
    assert client.post(f"{ORDERS}/{order['id']}/accept", headers=master_h).status_code == 200

    r = client.post(f"{ORDERS}/{order['id']}/cancel", headers=cust_h)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == OrderStatus.CANCELLED.value

    notes = client.get("/api/v1/notifications", headers=master_h).json()
    assert any(n["type"] == "order_cancelled" for n in notes)
    master_phone = db.get(models.User, mp.user_id).phone
    assert sms.last_message_for(master_phone) is not None


def test_cancel_unassigned_order_does_not_fail(client, db, signup, make_category):
    cat = make_category("Santexnik", "santexnik")
    cust_h, _ = signup("customer", "+998901112233", "Mijoz")
    order = _order(client, cust_h, cat.id)
    assert client.post(f"{ORDERS}/{order['id']}/cancel", headers=cust_h).status_code == 200


def test_chat_message_does_not_send_sms(client, db, signup, make_category):
    assert "new_message" not in SMS_NOTIFICATION_TYPES
    cat = make_category("Santexnik", "santexnik")
    cust_h, _ = signup("customer", "+998901112233", "Mijoz")
    master_h, mp = _master(db, signup, "+998902223344", "Usta", categories=[cat])
    order = _order(client, cust_h, cat.id)
    client.post(f"{ORDERS}/{order['id']}/select-master", json={"master_id": mp.id}, headers=cust_h)
    client.post(f"{ORDERS}/{order['id']}/accept", headers=master_h)

    master_phone = db.get(models.User, mp.user_id).phone
    before = sms.last_message_for(master_phone)
    r = client.post(f"{ORDERS}/{order['id']}/messages", json={"body": "Salom"}, headers=cust_h)
    assert r.status_code == 201, r.text
    assert sms.last_message_for(master_phone) == before


def test_dispatch_status_visible_to_offered_master_only(client, db, signup, make_category):
    cat = make_category("Santexnik", "santexnik")
    cust_h, _ = signup("customer", "+998901112233", "Mijoz")
    offered_h, mp = _master(db, signup, "+998902223344", "Taklif", categories=[cat])
    other_h, _ = _master(db, signup, "+998902223355", "Begona")
    order = _order(client, cust_h, cat.id, mode="automatic")

    url = f"{ORDERS}/{order['id']}/dispatch-status"
    assert client.get(url, headers=offered_h).status_code == 200
    assert client.get(url, headers=other_h).status_code == 404


def test_rotate_can_be_scoped_to_customer(client, db, signup, make_category):
    cat = make_category("Santexnik", "santexnik")
    a_h, a = signup("customer", "+998901112233", "Mijoz A")
    b_h, b = signup("customer", "+998901112244", "Mijoz B")
    oa = _order(client, a_h, cat.id, mode="automatic")
    ob = _order(client, b_h, cat.id, mode="automatic")
    _master(db, signup, "+998902223344", "Usta", categories=[cat])

    matching.rotate_stale_automatic_orders(db, customer_id=a["id"])
    db.commit()

    def offers(order_id):
        return db.query(models.OrderOffer).filter_by(order_id=order_id).count()

    assert offers(oa["id"]) == 1
    assert offers(ob["id"]) == 0
