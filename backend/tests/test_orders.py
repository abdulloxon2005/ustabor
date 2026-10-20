"""Buyurtma endpointlari uchun HTTP testlar."""

import pytest

ORDERS = "/api/v1/orders"

ORDER_BODY = {
    "description": "Kran oqyapti, tuzatish kerak",
    "city": "Toshkent",
    "district": "Chilonzor",
    "address": "Bunyodkor 1-uy",
    "selection_mode": "manual",
}


@pytest.fixture
def customer_a(signup):
    return signup("customer", "+998901111111", "Mijoz A")


@pytest.fixture
def customer_b(signup):
    return signup("customer", "+998901111112", "Mijoz B")


@pytest.fixture
def cat(make_category):
    return make_category("Santexnik", "santexnik")


def create_order(client, headers, cat_id, **overrides):
    return client.post(ORDERS, json={**ORDER_BODY, "category_id": cat_id, **overrides}, headers=headers)


# ---------- yaratish ----------

def test_create_order_ok(client, customer_a, cat):
    headers, user = customer_a
    r = create_order(client, headers, cat.id)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "searching"
    assert body["commission_rate"] == 10
    assert body["master_id"] is None
    assert body["agreed_price"] is None
    assert "commission_amount" not in body
    assert body["category_name"] == "Santexnik"
    assert body["customer_id"] == user["id"]
    assert body["selection_mode"] == "manual"
    # Birinchi tarix yozuvi
    assert len(body["history"]) == 1
    h = body["history"][0]
    assert h["from_status"] is None
    assert h["to_status"] == "searching"
    assert h["changed_by"] == user["id"]


def test_create_order_automatic_mode(client, customer_a, cat):
    headers, _ = customer_a
    r = create_order(client, headers, cat.id, selection_mode="automatic")
    assert r.status_code == 201
    assert r.json()["selection_mode"] == "automatic"


def test_master_and_anonymous_cannot_create(client, signup, cat):
    master_h, _ = signup("master", "+998902222222", "Usta")
    assert create_order(client, master_h, cat.id).status_code == 403
    assert client.post(ORDERS, json={**ORDER_BODY, "category_id": cat.id}).status_code == 401


def test_inactive_category_rejected(client, customer_a, make_category):
    headers, _ = customer_a
    dead = make_category("Eski", "eski", is_active=False)
    assert create_order(client, headers, dead.id).status_code == 422


def test_unknown_category_rejected(client, customer_a):
    headers, _ = customer_a
    assert create_order(client, headers, 9999).status_code == 422


def test_short_description_rejected(client, customer_a, cat):
    headers, _ = customer_a
    assert create_order(client, headers, cat.id, description="hi").status_code == 422


def test_empty_fields_rejected(client, customer_a, cat):
    headers, _ = customer_a
    for field in ("city", "district", "address"):
        assert create_order(client, headers, cat.id, **{field: "  "}).status_code == 422


def test_bad_selection_mode(client, customer_a, cat):
    headers, _ = customer_a
    assert create_order(client, headers, cat.id, selection_mode="random").status_code == 422


def test_protected_fields_ignored(client, customer_a, cat):
    headers, user = customer_a
    r = create_order(
        client, headers, cat.id,
        status="completed",
        master_id=999,
        agreed_price=50000,
        commission_rate=0,
        commission_amount=5000,
    )
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "searching"
    assert body["master_id"] is None
    assert body["agreed_price"] is None
    assert body["commission_rate"] == 10
    assert "commission_amount" not in body


# ---------- ro'yxat ----------

def test_list_own_orders(client, customer_a, customer_b, cat):
    ha, _ = customer_a
    hb, _ = customer_b
    create_order(client, ha, cat.id)
    create_order(client, ha, cat.id, description="Ikkinchi buyurtma")
    create_order(client, hb, cat.id, description="B mijozning buyurtmasi")
    r = client.get(ORDERS, headers=ha)
    assert r.status_code == 200
    assert len(r.json()) == 2
    # Yangilar birinchi (id desc)
    ids = [o["id"] for o in r.json()]
    assert ids == sorted(ids, reverse=True)

    r = client.get(ORDERS, headers=hb)
    assert len(r.json()) == 1


def test_list_status_filter(client, customer_a, cat):
    headers, _ = customer_a
    oid1 = create_order(client, headers, cat.id).json()["id"]
    create_order(client, headers, cat.id, description="Ikkinchi buyurtma")
    client.post(f"{ORDERS}/{oid1}/cancel", headers=headers)

    r = client.get(ORDERS, headers=headers, params={"status_filter": "searching"})
    assert len(r.json()) == 1
    r = client.get(ORDERS, headers=headers, params={"status_filter": "cancelled"})
    assert len(r.json()) == 1


def test_list_pagination(client, customer_a, cat):
    headers, _ = customer_a
    for i in range(5):
        create_order(client, headers, cat.id, description=f"Buyurtma {i} tavsifi")

    r = client.get(ORDERS, headers=headers, params={"limit": 2, "offset": 0})
    assert len(r.json()) == 2
    r = client.get(ORDERS, headers=headers, params={"limit": 2, "offset": 4})
    assert len(r.json()) == 1
    r = client.get(ORDERS, headers=headers, params={"limit": 200})  # max=100
    assert len(r.json()) == 5


def test_list_anonymous(client):
    assert client.get(ORDERS).status_code == 401


# ---------- tafsilot ----------

def test_get_order_ok(client, customer_a, cat):
    headers, _ = customer_a
    oid = create_order(client, headers, cat.id).json()["id"]
    r = client.get(f"{ORDERS}/{oid}", headers=headers)
    assert r.status_code == 200
    assert r.json()["id"] == oid
    assert r.json()["category_name"] == "Santexnik"
    assert len(r.json()["history"]) == 1


def test_get_order_stranger_404(client, customer_a, customer_b, cat):
    ha, _ = customer_a
    hb, _ = customer_b
    oid = create_order(client, ha, cat.id).json()["id"]
    assert client.get(f"{ORDERS}/{oid}", headers=hb).status_code == 404
    assert client.get(f"{ORDERS}/9999", headers=ha).status_code == 404


# ---------- bekor qilish ----------

def test_cancel_from_searching(client, customer_a, cat):
    headers, user = customer_a
    oid = create_order(client, headers, cat.id).json()["id"]
    r = client.post(f"{ORDERS}/{oid}/cancel", headers=headers)
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"
    assert len(r.json()["history"]) == 2
    h = r.json()["history"][-1]
    assert h["from_status"] == "searching"
    assert h["to_status"] == "cancelled"
    assert h["changed_by"] == user["id"]


def test_cancel_twice_409(client, customer_a, cat):
    headers, _ = customer_a
    oid = create_order(client, headers, cat.id).json()["id"]
    assert client.post(f"{ORDERS}/{oid}/cancel", headers=headers).status_code == 200
    r = client.post(f"{ORDERS}/{oid}/cancel", headers=headers)
    assert r.status_code == 409
    assert r.json()["detail"] == "Bu holatdan o'tish mumkin emas"


def test_cancel_stranger_404(client, customer_a, customer_b, cat):
    ha, _ = customer_a
    hb, _ = customer_b
    oid = create_order(client, ha, cat.id).json()["id"]
    assert client.post(f"{ORDERS}/{oid}/cancel", headers=hb).status_code == 404
