"""Pricing, Quotes, Start/Complete, and Earnings API testlari."""

from sqlalchemy import select

from app import models
from app.models.enums import OrderStatus, PaymentStatus, PricingType


def _create_master(db, user_id, cat_id, pricing_type=PricingType.FIXED, base_price=150_000, city="Toshkent"):
    mp = models.MasterProfile(
        user_id=user_id,
        bio="Test usta",
        city=city,
        district="Chilonzor",
        is_approved=True,
        is_available=True,
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


# ============================================================================
# 1. Fixed-price variant
# ============================================================================


def test_fixed_price_variant(client, db, signup, make_category):
    """Qat'iy narxli xizmat: usta qabul qilgach agreed_price avtomatik o'rnatiladi,
    to'g'ridan-to'g'ri boshlanadi va yakunlanadi."""
    cat = make_category("Santexnik", "santexnik")
    h_c, u_c = signup("customer", "+998901000001", "Mijoz 1")
    h_m, u_m = signup("master", "+998902000001", "Aziz Usta")
    mp = _create_master(db, u_m["id"], cat.id, pricing_type=PricingType.FIXED, base_price=150_000)

    # Buyurtma yaratish va ustani tanlash
    r_order = client.post(
        "/api/v1/orders",
        json={
            "category_id": cat.id,
            "description": "Kran almashtirish",
            "city": "Toshkent",
            "district": "Chilonzor",
            "address": "Navoiy 12",
            "selection_mode": "manual",
        },
        headers=h_c,
    )
    oid = r_order.json()["id"]

    client.post(f"/api/v1/orders/{oid}/select-master", json={"master_id": mp.id}, headers=h_c)

    # Usta qabul qiladi -> agreed_price = 150_000 avtomatik o'rnatiladi
    r_accept = client.post(f"/api/v1/orders/{oid}/accept", headers=h_m)
    assert r_accept.status_code == 200

    r_get = client.get(f"/api/v1/orders/{oid}", headers=h_c)
    assert r_get.status_code == 200
    assert r_get.json()["agreed_price"] == 150_000

    # Usta quote berishi shart emas, to'g'ridan-to'g'ri boshlaydi
    r_start = client.post(f"/api/v1/orders/{oid}/start", headers=h_m)
    assert r_start.status_code == 200
    assert r_start.json()["status"] == "in_progress"

    # Yakunlash
    r_complete = client.post(f"/api/v1/orders/{oid}/complete", headers=h_m)
    assert r_complete.status_code == 200
    res = r_complete.json()
    assert res["price"] == 150_000
    assert res["commission_rate"] == 10
    assert res["commission_amount"] == 15_000
    assert res["net"] == 135_000


# ============================================================================
# 2. Price Protection
# ============================================================================


def test_start_without_confirmed_price_409(client, db, signup, make_category):
    """Narx tasdiqlanmasdan start_order chaqirilsa -> 409."""
    cat = make_category("Elektrik", "elektrik")
    h_c, _ = signup("customer", "+998901000002", "Mijoz 2")
    h_m, u_m = signup("master", "+998902000002", "Bobur Usta")
    mp = _create_master(db, u_m["id"], cat.id, pricing_type=PricingType.QUOTE, base_price=None)

    r_order = client.post(
        "/api/v1/orders",
        json={
            "category_id": cat.id,
            "description": "Simlarni ulash",
            "city": "Toshkent",
            "district": "Chilonzor",
            "address": "Navoiy 13",
            "selection_mode": "manual",
        },
        headers=h_c,
    )
    oid = r_order.json()["id"]
    client.post(f"/api/v1/orders/{oid}/select-master", json={"master_id": mp.id}, headers=h_c)
    client.post(f"/api/v1/orders/{oid}/accept", headers=h_m)

    # Narx tasdiqlanmasdan start -> 409
    r_start = client.post(f"/api/v1/orders/{oid}/start", headers=h_m)
    assert r_start.status_code == 409
    assert "narx" in r_start.json()["detail"].lower()


def test_customer_cannot_accept_quote_of_other_customer_404(client, db, signup, make_category):
    """Begona mijoz boshqa mijozning taklifini tasdiqlay olmaydi -> 404."""
    cat = make_category("Santexnik", "santexnik")
    h_c1, _ = signup("customer", "+998901000003", "Mijoz 1")
    h_c2, _ = signup("customer", "+998901000004", "Mijoz 2 (begona)")
    h_m, u_m = signup("master", "+998902000003", "Usta")
    mp = _create_master(db, u_m["id"], cat.id, pricing_type=PricingType.QUOTE, base_price=None)

    r_order = client.post(
        "/api/v1/orders",
        json={
            "category_id": cat.id,
            "description": "Kran tuzatish",
            "city": "Toshkent",
            "district": "Chilonzor",
            "address": "Manzil",
            "selection_mode": "manual",
        },
        headers=h_c1,
    )
    oid = r_order.json()["id"]
    client.post(f"/api/v1/orders/{oid}/select-master", json={"master_id": mp.id}, headers=h_c1)
    client.post(f"/api/v1/orders/{oid}/accept", headers=h_m)

    r_quote = client.post(f"/api/v1/orders/{oid}/quotes", json={"price": 100_000}, headers=h_m)
    qid = r_quote.json()["id"]

    # Begona mijoz -> 404
    r_stranger_accept = client.post(f"/api/v1/orders/{oid}/quotes/{qid}/accept", headers=h_c2)
    assert r_stranger_accept.status_code == 404
    assert r_stranger_accept.json()["detail"] == "Buyurtma topilmadi"

    # Begona mijoz reject -> 404
    r_stranger_reject = client.post(f"/api/v1/orders/{oid}/quotes/{qid}/reject", headers=h_c2)
    assert r_stranger_reject.status_code == 404


def test_stranger_master_cannot_quote_start_complete_404(client, db, signup, make_category):
    """Biriktirilmagan begona usta quote/start/complete chaqira olmaydi -> 404."""
    cat = make_category("Santexnik", "santexnik")
    h_c, _ = signup("customer", "+998901000005", "Mijoz")
    h_m1, u_m1 = signup("master", "+998902000004", "Biriktirilgan Usta")
    h_m2, u_m2 = signup("master", "+998902000005", "Begona Usta")
    mp1 = _create_master(db, u_m1["id"], cat.id, pricing_type=PricingType.QUOTE)
    _create_master(db, u_m2["id"], cat.id, pricing_type=PricingType.QUOTE)

    r_order = client.post(
        "/api/v1/orders",
        json={
            "category_id": cat.id,
            "description": "Kran ta'miri",
            "city": "Toshkent",
            "district": "Chilonzor",
            "address": "Manzil",
            "selection_mode": "manual",
        },
        headers=h_c,
    )
    oid = r_order.json()["id"]
    client.post(f"/api/v1/orders/{oid}/select-master", json={"master_id": mp1.id}, headers=h_c)
    client.post(f"/api/v1/orders/{oid}/accept", headers=h_m1)

    # Begona usta quote -> 404
    r_q = client.post(f"/api/v1/orders/{oid}/quotes", json={"price": 80_000}, headers=h_m2)
    assert r_q.status_code == 404
    assert r_q.json()["detail"] == "Buyurtma topilmadi"

    # Begona usta start -> 404
    r_s = client.post(f"/api/v1/orders/{oid}/start", headers=h_m2)
    assert r_s.status_code == 404

    # Begona usta complete -> 404
    r_c = client.post(f"/api/v1/orders/{oid}/complete", headers=h_m2)
    assert r_c.status_code == 404


def test_second_quote_replaces_first(client, db, signup, make_category):
    """Ikkinchi narx taklifi birinchisini almashtiradi (birinchisi rejected bo'ladi)."""
    cat = make_category("Santexnik", "santexnik")
    h_c, _ = signup("customer", "+998901000006", "Mijoz")
    h_m, u_m = signup("master", "+998902000006", "Usta")
    mp = _create_master(db, u_m["id"], cat.id, pricing_type=PricingType.QUOTE)

    r_order = client.post(
        "/api/v1/orders",
        json={
            "category_id": cat.id,
            "description": "Kran ta'miri",
            "city": "Toshkent",
            "district": "Chilonzor",
            "address": "Manzil",
            "selection_mode": "manual",
        },
        headers=h_c,
    )
    oid = r_order.json()["id"]
    client.post(f"/api/v1/orders/{oid}/select-master", json={"master_id": mp.id}, headers=h_c)
    client.post(f"/api/v1/orders/{oid}/accept", headers=h_m)

    # Birinchi quote: 100_000
    r_q1 = client.post(f"/api/v1/orders/{oid}/quotes", json={"price": 100_000, "note": "1-taklif"}, headers=h_m)
    assert r_q1.status_code == 201
    q1_id = r_q1.json()["id"]

    # Ikkinchi quote: 120_000
    r_q2 = client.post(f"/api/v1/orders/{oid}/quotes", json={"price": 120_000, "note": "2-taklif"}, headers=h_m)
    assert r_q2.status_code == 201
    q2_id = r_q2.json()["id"]

    # Mijoz buyurtmani tekshiradi: q1 rejected, q2 proposed
    r_get = client.get(f"/api/v1/orders/{oid}", headers=h_c)
    quotes = r_get.json()["quotes"]
    assert len(quotes) == 2
    q1_dict = next(q for q in quotes if q["id"] == q1_id)
    q2_dict = next(q for q in quotes if q["id"] == q2_id)
    assert q1_dict["status"] == "rejected"
    assert q2_dict["status"] == "proposed"

    # Eskisini tasdiqlash -> 409
    r_old_accept = client.post(f"/api/v1/orders/{oid}/quotes/{q1_id}/accept", headers=h_c)
    assert r_old_accept.status_code == 409


def test_quote_after_price_fixed_returns_409(client, db, signup, make_category):
    """Narx tasdiqlangandan so'ng yangi taklif yuborish -> 409."""
    cat = make_category("Santexnik", "santexnik")
    h_c, _ = signup("customer", "+998901000007", "Mijoz")
    h_m, u_m = signup("master", "+998902000007", "Usta")
    mp = _create_master(db, u_m["id"], cat.id, pricing_type=PricingType.FIXED, base_price=100_000)

    r_order = client.post(
        "/api/v1/orders",
        json={
            "category_id": cat.id,
            "description": "Kran ta'miri",
            "city": "Toshkent",
            "district": "Chilonzor",
            "address": "Manzil",
            "selection_mode": "manual",
        },
        headers=h_c,
    )
    oid = r_order.json()["id"]
    client.post(f"/api/v1/orders/{oid}/select-master", json={"master_id": mp.id}, headers=h_c)
    client.post(f"/api/v1/orders/{oid}/accept", headers=h_m)

    # Qat'iy narx allaqachon tasdiqlangan (100_000) -> yangi quote berish 409
    r_quote = client.post(f"/api/v1/orders/{oid}/quotes", json={"price": 150_000}, headers=h_m)
    assert r_quote.status_code == 409


def test_quote_validation_errors_422(client, db, signup, make_category):
    """Narx 0, manfiy, float, string, juda katta -> 422."""
    cat = make_category("Santexnik", "santexnik")
    h_c, _ = signup("customer", "+998901000008", "Mijoz")
    h_m, u_m = signup("master", "+998902000008", "Usta")
    mp = _create_master(db, u_m["id"], cat.id, pricing_type=PricingType.QUOTE)

    r_order = client.post(
        "/api/v1/orders",
        json={
            "category_id": cat.id,
            "description": "Kran ta'miri",
            "city": "Toshkent",
            "district": "Chilonzor",
            "address": "Manzil",
            "selection_mode": "manual",
        },
        headers=h_c,
    )
    oid = r_order.json()["id"]
    client.post(f"/api/v1/orders/{oid}/select-master", json={"master_id": mp.id}, headers=h_c)
    client.post(f"/api/v1/orders/{oid}/accept", headers=h_m)

    # price = 0 -> 422
    assert client.post(f"/api/v1/orders/{oid}/quotes", json={"price": 0}, headers=h_m).status_code == 422
    # price = -5000 -> 422
    assert client.post(f"/api/v1/orders/{oid}/quotes", json={"price": -5000}, headers=h_m).status_code == 422
    # float price -> 422
    assert client.post(f"/api/v1/orders/{oid}/quotes", json={"price": 100000.5}, headers=h_m).status_code == 422
    # too large price (> 100_000_000) -> 422
    assert client.post(f"/api/v1/orders/{oid}/quotes", json={"price": 100_000_001}, headers=h_m).status_code == 422


def test_client_sent_agreed_price_and_commission_ignored(client, db, signup, make_category):
    """Mijoz yoki usta yuborgan status/agreed_price/commission maydonlari e'tiborga olinmaydi."""
    cat = make_category("Santexnik", "santexnik")
    h_c, _ = signup("customer", "+998901000009", "Mijoz")
    h_m, u_m = signup("master", "+998902000009", "Usta")
    mp = _create_master(db, u_m["id"], cat.id, pricing_type=PricingType.QUOTE)

    r_order = client.post(
        "/api/v1/orders",
        json={
            "category_id": cat.id,
            "description": "Kran ta'miri",
            "city": "Toshkent",
            "district": "Chilonzor",
            "address": "Manzil",
            "selection_mode": "manual",
            "agreed_price": 50000,
            "commission_rate": 0,
            "commission_amount": 0,
            "status": "completed",
        },
        headers=h_c,
    )
    oid = r_order.json()["id"]
    client.post(f"/api/v1/orders/{oid}/select-master", json={"master_id": mp.id}, headers=h_c)
    client.post(f"/api/v1/orders/{oid}/accept", headers=h_m)

    r_quote = client.post(
        f"/api/v1/orders/{oid}/quotes",
        json={
            "price": 200_000,
            "agreed_price": 50_000,
            "status": "accepted",
            "commission_amount": 0,
        },
        headers=h_m,
    )
    assert r_quote.status_code == 201
    assert r_quote.json()["status"] == "proposed"
    assert r_quote.json()["price"] == 200_000


# ============================================================================
# 3. Completion Edge Cases
# ============================================================================


def test_second_complete_returns_409_and_still_one_payment(client, db, signup, make_category):
    """Ikkinchi marta complete chaqirilsa 409 va baribir bitta to'lov qoladi."""
    cat = make_category("Santexnik", "santexnik")
    h_c, _ = signup("customer", "+998901000010", "Mijoz")
    h_m, u_m = signup("master", "+998902000010", "Usta")
    mp = _create_master(db, u_m["id"], cat.id, pricing_type=PricingType.FIXED, base_price=100_000)

    r_order = client.post(
        "/api/v1/orders",
        json={
            "category_id": cat.id,
            "description": "Kran ta'miri",
            "city": "Toshkent",
            "district": "Chilonzor",
            "address": "Manzil",
            "selection_mode": "manual",
        },
        headers=h_c,
    )
    oid = r_order.json()["id"]
    client.post(f"/api/v1/orders/{oid}/select-master", json={"master_id": mp.id}, headers=h_c)
    client.post(f"/api/v1/orders/{oid}/accept", headers=h_m)
    client.post(f"/api/v1/orders/{oid}/start", headers=h_m)

    # Birinchi complete -> 200
    r_c1 = client.post(f"/api/v1/orders/{oid}/complete", headers=h_m)
    assert r_c1.status_code == 200

    # Ikkinchi complete -> 409
    r_c2 = client.post(f"/api/v1/orders/{oid}/complete", headers=h_m)
    assert r_c2.status_code == 409

    # To'lov baribir bitta
    payments = db.scalars(select(models.Payment).where(models.Payment.order_id == oid)).all()
    assert len(payments) == 1


def test_cancelled_order_cannot_be_completed(client, db, signup, make_category):
    """Bekor qilingan buyurtma yakunlanishi mumkin emas -> 409."""
    cat = make_category("Santexnik", "santexnik")
    h_c, _ = signup("customer", "+998901000011", "Mijoz")
    h_m, u_m = signup("master", "+998902000011", "Usta")
    mp = _create_master(db, u_m["id"], cat.id, pricing_type=PricingType.FIXED, base_price=100_000)

    r_order = client.post(
        "/api/v1/orders",
        json={
            "category_id": cat.id,
            "description": "Kran ta'miri",
            "city": "Toshkent",
            "district": "Chilonzor",
            "address": "Manzil",
            "selection_mode": "manual",
        },
        headers=h_c,
    )
    oid = r_order.json()["id"]
    client.post(f"/api/v1/orders/{oid}/cancel", headers=h_c)

    r_comp = client.post(f"/api/v1/orders/{oid}/complete", headers=h_m)
    # Begona yoki bekor qilingan (biriktirilmagan) -> 404
    assert r_comp.status_code == 404


def test_role_restrictions_and_anonymous_auth(client, db, signup, make_category):
    """Mijoz start/complete chaqira olmaydi (403), anonim (401)."""
    cat = make_category("Santexnik", "santexnik")
    h_c, _ = signup("customer", "+998901000012", "Mijoz")

    # Mijoz start va complete chaqirishi mumkin emas -> 403
    assert client.post("/api/v1/orders/1/start", headers=h_c).status_code == 403
    assert client.post("/api/v1/orders/1/complete", headers=h_c).status_code == 403
    assert client.post("/api/v1/orders/1/quotes", json={"price": 100000}, headers=h_c).status_code == 403
    assert client.get("/api/v1/masters/me/earnings", headers=h_c).status_code == 403

    # Anonim -> 401
    assert client.post("/api/v1/orders/1/start").status_code == 401
    assert client.post("/api/v1/orders/1/complete").status_code == 401
    assert client.post("/api/v1/orders/1/quotes", json={"price": 100000}).status_code == 401
    assert client.get("/api/v1/masters/me/earnings").status_code == 401


# ============================================================================
# 4. Security & Earnings Isolation
# ============================================================================


def test_customer_order_json_never_contains_commission_amount(client, db, signup, make_category):
    """Mijoz buyurtma JSON'ida hech qachon commission_amount bo'lmaydi."""
    cat = make_category("Santexnik", "santexnik")
    h_c, _ = signup("customer", "+998901000013", "Mijoz")
    h_m, u_m = signup("master", "+998902000013", "Usta")
    mp = _create_master(db, u_m["id"], cat.id, pricing_type=PricingType.FIXED, base_price=200_000)

    r_order = client.post(
        "/api/v1/orders",
        json={
            "category_id": cat.id,
            "description": "Kran ta'miri",
            "city": "Toshkent",
            "district": "Chilonzor",
            "address": "Manzil",
            "selection_mode": "manual",
        },
        headers=h_c,
    )
    oid = r_order.json()["id"]
    client.post(f"/api/v1/orders/{oid}/select-master", json={"master_id": mp.id}, headers=h_c)
    client.post(f"/api/v1/orders/{oid}/accept", headers=h_m)
    client.post(f"/api/v1/orders/{oid}/start", headers=h_m)
    client.post(f"/api/v1/orders/{oid}/complete", headers=h_m)

    r_get = client.get(f"/api/v1/orders/{oid}", headers=h_c)
    assert r_get.status_code == 200
    data = r_get.json()
    assert "commission_amount" not in data
    assert "commission_total" not in data
    assert "net" not in data
    assert "net_amount" not in data


def test_earnings_isolation_between_two_masters(client, db, signup, make_category):
    """Daromad faqat chaqiruvchi ustaning o'ziga tegishli (izolyatsiya)."""
    cat = make_category("Santexnik", "santexnik")
    h_c, _ = signup("customer", "+998901000014", "Mijoz")
    h_m1, u_m1 = signup("master", "+998902000014", "Usta 1")
    h_m2, u_m2 = signup("master", "+998902000015", "Usta 2")
    mp1 = _create_master(db, u_m1["id"], cat.id, pricing_type=PricingType.FIXED, base_price=100_000)
    mp2 = _create_master(db, u_m2["id"], cat.id, pricing_type=PricingType.FIXED, base_price=300_000)

    # Usta 1 uchun buyurtma
    r1 = client.post(
        "/api/v1/orders",
        json={
            "category_id": cat.id,
            "description": "1-buyurtma",
            "city": "Toshkent",
            "district": "Chilonzor",
            "address": "Manzil 1",
            "selection_mode": "manual",
        },
        headers=h_c,
    )
    o1 = r1.json()["id"]
    client.post(f"/api/v1/orders/{o1}/select-master", json={"master_id": mp1.id}, headers=h_c)
    client.post(f"/api/v1/orders/{o1}/accept", headers=h_m1)
    client.post(f"/api/v1/orders/{o1}/start", headers=h_m1)
    client.post(f"/api/v1/orders/{o1}/complete", headers=h_m1)

    # Usta 2 uchun buyurtma
    r2 = client.post(
        "/api/v1/orders",
        json={
            "category_id": cat.id,
            "description": "2-buyurtma",
            "city": "Toshkent",
            "district": "Chilonzor",
            "address": "Manzil 2",
            "selection_mode": "manual",
        },
        headers=h_c,
    )
    o2 = r2.json()["id"]
    client.post(f"/api/v1/orders/{o2}/select-master", json={"master_id": mp2.id}, headers=h_c)
    client.post(f"/api/v1/orders/{o2}/accept", headers=h_m2)
    client.post(f"/api/v1/orders/{o2}/start", headers=h_m2)
    client.post(f"/api/v1/orders/{o2}/complete", headers=h_m2)

    # Usta 1 earnings tekshiruvi: faqat 100_000
    e1 = client.get("/api/v1/masters/me/earnings", headers=h_m1).json()
    assert e1["completed_count"] == 1
    assert e1["gross_total"] == 100_000
    assert e1["commission_total"] == 10_000
    assert e1["net_total"] == 90_000
    assert len(e1["orders"]) == 1
    assert e1["orders"][0]["id"] == o1

    # Usta 2 earnings tekshiruvi: faqat 300_000
    e2 = client.get("/api/v1/masters/me/earnings", headers=h_m2).json()
    assert e2["completed_count"] == 1
    assert e2["gross_total"] == 300_000
    assert e2["commission_total"] == 30_000
    assert e2["net_total"] == 270_000
    assert len(e2["orders"]) == 1
    assert e2["orders"][0]["id"] == o2
