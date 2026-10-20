"""Assignment API testlari:
- automatic order offer creation (va note holati)
- manual select-master (happy path, 404 stranger, 409 automatic, ineligible, duplicate pending)
- master accept (happy path, stranger 404, customer/anon 403/401, unapproved 403, expired 409, race condition 409)
- master reject (automatic rejimda navbatdagi ustaga, hech kim qolmasa searching, manual rejimda faqat offer o'zgaradi)
- GET /masters/me/orders (pending offers manzil yashirilgan, active orders manzil ko'rsatilgan, begona usta narsalari yo'q)
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app import models
from app.models.enums import OfferStatus, OrderStatus, PricingType, Role, SelectionMode

ORDERS_URL = "/api/v1/orders"
MASTERS_URL = "/api/v1/masters"


@pytest.fixture
def santexnik_cat(make_category):
    return make_category("Santexnik", "santexnik")


@pytest.fixture
def elektrik_cat(make_category):
    return make_category("Elektrik", "elektrik")


def _create_master_profile(db, user_id, city="Toshkent", district="Chilonzor", is_approved=True, is_available=True, rating_avg=4.5, rating_count=10):
    mp = models.MasterProfile(
        user_id=user_id,
        city=city,
        district=district,
        is_approved=is_approved,
        is_available=is_available,
        rating_avg=rating_avg,
        rating_count=rating_count,
    )
    db.add(mp)
    db.commit()
    db.refresh(mp)
    return mp


def _add_service(db, master_id, category_id, pricing_type=PricingType.FIXED, base_price=100_000):
    ms = models.MasterService(
        master_id=master_id,
        category_id=category_id,
        pricing_type=pricing_type,
        base_price=base_price,
    )
    db.add(ms)
    db.commit()
    db.refresh(ms)
    return ms


# ============================================================================
# 1. Automatic order: offer creation va note
# ============================================================================


def test_automatic_order_creates_offer_for_best_eligible_master(client, db, signup, santexnik_cat):
    """Automatic order eligible ustalar ichidan eng yaxshisiga bitta pending offer yaratadi.
    Tasdiqlanmagan yoki mavjud bo'lmagan usta taklif qilinmaydi."""
    # Usta 1: tasdiqlangan, mavjud, santexnik
    h_m1, u_m1 = signup("master", "+998902000001", "Aziz Usta")
    m1 = _create_master_profile(db, u_m1["id"], is_approved=True, is_available=True, rating_avg=4.8, rating_count=20)
    _add_service(db, m1.id, santexnik_cat.id)

    # Usta 2: tasdiqlanmagan
    h_m2, u_m2 = signup("master", "+998902000002", "Vali Usta")
    m2 = _create_master_profile(db, u_m2["id"], is_approved=False, is_available=True)
    _add_service(db, m2.id, santexnik_cat.id)

    # Mijoz buyurtma beradi
    h_c, u_c = signup("customer", "+998901000001", "Mijoz Ali")
    r = client.post(
        ORDERS_URL,
        json={
            "category_id": santexnik_cat.id,
            "description": "Kran tuzatish kerak",
            "city": "Toshkent",
            "district": "Chilonzor",
            "address": "Navoiy 1",
            "selection_mode": "automatic",
        },
        headers=h_c,
    )
    assert r.status_code == 201
    data = r.json()
    assert data["status"] == "searching"
    assert data["note"] is None
    assert len(data["offers"]) == 1
    assert data["offers"][0]["master_id"] == m1.id
    assert data["offers"][0]["status"] == "pending"


def test_automatic_order_no_eligible_master_returns_note(client, db, signup, santexnik_cat):
    """Mos usta topilmasa buyurtma searching holatida yaratiladi va note qaytadi."""
    h_c, u_c = signup("customer", "+998901000002", "Mijoz Sobir")
    r = client.post(
        ORDERS_URL,
        json={
            "category_id": santexnik_cat.id,
            "description": "Kran tuzatish kerak",
            "city": "Samarqand",  # Samarqandda hech kim yo'q
            "district": "Markaz",
            "address": "Registon 1",
            "selection_mode": "automatic",
        },
        headers=h_c,
    )
    assert r.status_code == 201
    data = r.json()
    assert data["status"] == "searching"
    assert data["note"] == "Mos usta topilmadi"
    assert len(data["offers"]) == 0


# ============================================================================
# 2. Manual select-master
# ============================================================================


def test_manual_select_master_happy_path(client, db, signup, santexnik_cat):
    """Mijoz manual buyurtmaga mos ustani tanlaydi."""
    h_m, u_m = signup("master", "+998902000003", "Jasur Usta")
    mp = _create_master_profile(db, u_m["id"], city="Toshkent", district="Chilonzor")
    _add_service(db, mp.id, santexnik_cat.id)

    h_c, u_c = signup("customer", "+998901000003", "Mijoz")
    r_order = client.post(
        ORDERS_URL,
        json={
            "category_id": santexnik_cat.id,
            "description": "Kran yangilash",
            "city": "Toshkent",
            "district": "Chilonzor",
            "address": "Amir Temur 5",
            "selection_mode": "manual",
        },
        headers=h_c,
    )
    order_id = r_order.json()["id"]

    # Usta tanlash
    r_select = client.post(
        f"{ORDERS_URL}/{order_id}/select-master",
        json={"master_id": mp.id},
        headers=h_c,
    )
    assert r_select.status_code == 200
    assert r_select.json()["detail"] == "Taklif yuborildi"


def test_manual_select_master_errors(client, db, signup, santexnik_cat, elektrik_cat):
    """Begona mijoz 404, automatic rejim 409, mos bo'lmagan usta 409, takroriy taklif 409."""
    h_m, u_m = signup("master", "+998902000004", "Akbar Usta")
    mp = _create_master_profile(db, u_m["id"], city="Toshkent", district="Chilonzor")
    _add_service(db, mp.id, santexnik_cat.id)

    h_c1, u_c1 = signup("customer", "+998901000004", "Mijoz 1")
    h_c2, u_c2 = signup("customer", "+998901000005", "Mijoz 2 (begona)")

    # Manual buyurtma
    r_order = client.post(
        ORDERS_URL,
        json={
            "category_id": santexnik_cat.id,
            "description": "Kran tuzatish",
            "city": "Toshkent",
            "district": "Chilonzor",
            "address": "Ko'cha 1",
            "selection_mode": "manual",
        },
        headers=h_c1,
    )
    order_id = r_order.json()["id"]

    # Begona mijoz -> 404
    r_stranger = client.post(
        f"{ORDERS_URL}/{order_id}/select-master",
        json={"master_id": mp.id},
        headers=h_c2,
    )
    assert r_stranger.status_code == 404

    # Automatic buyurtma uchun select-master -> 409
    r_auto = client.post(
        ORDERS_URL,
        json={
            "category_id": santexnik_cat.id,
            "description": "Avtomatik buyurtma",
            "city": "Toshkent",
            "district": "Chilonzor",
            "address": "Ko'cha 2",
            "selection_mode": "automatic",
        },
        headers=h_c1,
    )
    auto_id = r_auto.json()["id"]
    r_auto_select = client.post(
        f"{ORDERS_URL}/{auto_id}/select-master",
        json={"master_id": mp.id},
        headers=h_c1,
    )
    assert r_auto_select.status_code == 409

    # Boshqa shahardagi usta -> 409
    h_m_other, u_m_other = signup("master", "+998902000005", "Samarqandlik Usta")
    mp_other = _create_master_profile(db, u_m_other["id"], city="Samarqand")
    _add_service(db, mp_other.id, santexnik_cat.id)
    r_wrong_city = client.post(
        f"{ORDERS_URL}/{order_id}/select-master",
        json={"master_id": mp_other.id},
        headers=h_c1,
    )
    assert r_wrong_city.status_code == 409

    # Birinchi muvaffaqiyatli tanlash
    r_ok = client.post(
        f"{ORDERS_URL}/{order_id}/select-master",
        json={"master_id": mp.id},
        headers=h_c1,
    )
    assert r_ok.status_code == 200

    # Pending taklif mavjud bo'lganda ikkinchi tanlash -> 409 "Avvalgi taklifga javob kutilmoqda"
    h_m3, u_m3 = signup("master", "+998902000006", "Usta 3")
    mp3 = _create_master_profile(db, u_m3["id"], city="Toshkent")
    _add_service(db, mp3.id, santexnik_cat.id)
    r_pending_dup = client.post(
        f"{ORDERS_URL}/{order_id}/select-master",
        json={"master_id": mp3.id},
        headers=h_c1,
    )
    assert r_pending_dup.status_code == 409
    assert "Avvalgi taklifga javob kutilmoqda" in r_pending_dup.json()["detail"]


# ============================================================================
# 3. Master accepts
# ============================================================================


def test_master_accept_happy_path(client, db, signup, santexnik_cat):
    """Usta taklifni qabul qiladi: order assigned, master_id o'rnatiladi, history yoziladi,
    mijoz ustaning ismini ko'radi."""
    h_m, u_m = signup("master", "+998902000010", "Rustam Usta")
    mp = _create_master_profile(db, u_m["id"], city="Toshkent", district="Chilonzor")
    _add_service(db, mp.id, santexnik_cat.id)

    h_c, u_c = signup("customer", "+998901000010", "Mijoz Botir")
    r_order = client.post(
        ORDERS_URL,
        json={
            "category_id": santexnik_cat.id,
            "description": "Quvurni ta'mirlash",
            "city": "Toshkent",
            "district": "Chilonzor",
            "address": "Qatortol 10",
            "selection_mode": "manual",
        },
        headers=h_c,
    )
    order_id = r_order.json()["id"]

    # Mijoz ustani tanlaydi
    client.post(f"{ORDERS_URL}/{order_id}/select-master", json={"master_id": mp.id}, headers=h_c)

    # Usta qabul qiladi
    r_accept = client.post(f"{ORDERS_URL}/{order_id}/accept", headers=h_m)
    assert r_accept.status_code == 200

    # Mijoz buyurtmani tekshiradi
    r_get = client.get(f"{ORDERS_URL}/{order_id}", headers=h_c)
    assert r_get.status_code == 200
    data = r_get.json()
    assert data["status"] == "assigned"
    assert data["master_id"] == mp.id
    assert data["master_name"] == "Rustam Usta"


def test_master_accept_auth_and_permissions(client, db, signup, santexnik_cat):
    """Begona usta 404, mijoz yoki anonim 403/401, tasdiqlanmagan usta 403."""
    h_m1, u_m1 = signup("master", "+998902000011", "Usta 1")
    mp1 = _create_master_profile(db, u_m1["id"])
    _add_service(db, mp1.id, santexnik_cat.id)

    # Begona usta (taklif olmagan)
    h_m2, u_m2 = signup("master", "+998902000012", "Begona Usta")
    mp2 = _create_master_profile(db, u_m2["id"])
    _add_service(db, mp2.id, santexnik_cat.id)

    # Tasdiqlanmagan usta
    h_m_unapp, u_m_unapp = signup("master", "+998902000013", "Tasdiqsiz Usta")
    mp_unapp = _create_master_profile(db, u_m_unapp["id"], is_approved=False)
    _add_service(db, mp_unapp.id, santexnik_cat.id)

    h_c, u_c = signup("customer", "+998901000011", "Mijoz")
    r_order = client.post(
        ORDERS_URL,
        json={
            "category_id": santexnik_cat.id,
            "description": "Sinov buyurtma",
            "city": "Toshkent",
            "district": "Chilonzor",
            "address": "Ko'cha 3",
            "selection_mode": "manual",
        },
        headers=h_c,
    )
    order_id = r_order.json()["id"]
    client.post(f"{ORDERS_URL}/{order_id}/select-master", json={"master_id": mp1.id}, headers=h_c)

    # Begona usta qabul qilmoqchi -> 404
    r_stranger = client.post(f"{ORDERS_URL}/{order_id}/accept", headers=h_m2)
    assert r_stranger.status_code == 404

    # Anonim -> 401
    r_anon = client.post(f"{ORDERS_URL}/{order_id}/accept")
    assert r_anon.status_code == 401

    # Mijoz -> 403
    r_cust = client.post(f"{ORDERS_URL}/{order_id}/accept", headers=h_c)
    assert r_cust.status_code == 403

    # Tasdiqlanmagan usta -> 403
    r_unapp = client.post(f"{ORDERS_URL}/{order_id}/accept", headers=h_m_unapp)
    assert r_unapp.status_code == 403


def test_expired_offer_accept_returns_409(client, db, signup, santexnik_cat):
    """Muddati o'tgan taklif qabul qilinmoqchi bo'lsa -> 409 va status expired qilinadi."""
    h_m, u_m = signup("master", "+998902000014", "Kech qolgan usta")
    mp = _create_master_profile(db, u_m["id"])
    _add_service(db, mp.id, santexnik_cat.id)

    h_c, u_c = signup("customer", "+998901000012", "Mijoz")
    r_order = client.post(
        ORDERS_URL,
        json={
            "category_id": santexnik_cat.id,
            "description": "Shoshilinch ish",
            "city": "Toshkent",
            "district": "Chilonzor",
            "address": "Ko'cha 4",
            "selection_mode": "manual",
        },
        headers=h_c,
    )
    order_id = r_order.json()["id"]

    # DB ga muddati o'tgan taklif qo'shamiz
    stale_offer = models.OrderOffer(
        order_id=order_id,
        master_id=mp.id,
        status=OfferStatus.PENDING,
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=10),
    )
    db.add(stale_offer)
    db.commit()

    r = client.post(f"{ORDERS_URL}/{order_id}/accept", headers=h_m)
    assert r.status_code == 409
    assert "Taklif muddati tugagan" in r.json()["detail"]

    # Baza yangilanganini tekshirish
    db.refresh(stale_offer)
    assert stale_offer.status == OfferStatus.EXPIRED


def test_race_condition_two_masters_accept(client, db, signup, santexnik_cat):
    """RACE: Bitta buyurtmaga 2 ta taklif qo'yiladi. Master A qabul qiladi (200),
    keyin Master B qabul qilmoqchi bo'ladi -> 409 va buyurtma Master A ga tegishli bo'lib qoladi."""
    h_mA, u_mA = signup("master", "+998902000020", "Usta A")
    mpA = _create_master_profile(db, u_mA["id"])
    _add_service(db, mpA.id, santexnik_cat.id)

    h_mB, u_mB = signup("master", "+998902000021", "Usta B")
    mpB = _create_master_profile(db, u_mB["id"])
    _add_service(db, mpB.id, santexnik_cat.id)

    h_c, u_c = signup("customer", "+998901000020", "Mijoz")
    r_order = client.post(
        ORDERS_URL,
        json={
            "category_id": santexnik_cat.id,
            "description": "Katta ish",
            "city": "Toshkent",
            "district": "Chilonzor",
            "address": "Ko'cha 5",
            "selection_mode": "manual",
        },
        headers=h_c,
    )
    order_id = r_order.json()["id"]

    # Ikkala ustaga to'g'ridan-to'g'ri pending offer qo'shamiz
    future = datetime.now(timezone.utc) + timedelta(minutes=30)
    db.add(models.OrderOffer(order_id=order_id, master_id=mpA.id, status=OfferStatus.PENDING, expires_at=future))
    db.add(models.OrderOffer(order_id=order_id, master_id=mpB.id, status=OfferStatus.PENDING, expires_at=future))
    db.commit()

    # Usta A qabul qiladi -> 200
    rA = client.post(f"{ORDERS_URL}/{order_id}/accept", headers=h_mA)
    assert rA.status_code == 200

    # Usta B qabul qilmoqchi bo'ladi -> 409
    rB = client.post(f"{ORDERS_URL}/{order_id}/accept", headers=h_mB)
    assert rB.status_code == 409

    # Buyurtma Usta A da qoladi
    order = db.get(models.Order, order_id)
    assert order.status == OrderStatus.ASSIGNED
    assert order.master_id == mpA.id


# ============================================================================
# 4. Master rejects
# ============================================================================


def test_reject_in_automatic_mode_offers_next_master(client, db, signup, santexnik_cat):
    """Automatic rejimda rad etilganda darhol navbatdagi ustaga taklif yuboriladi."""
    h_m1, u_m1 = signup("master", "+998902000031", "Usta 1")
    mp1 = _create_master_profile(db, u_m1["id"], rating_avg=4.9, rating_count=30)
    _add_service(db, mp1.id, santexnik_cat.id)

    h_m2, u_m2 = signup("master", "+998902000032", "Usta 2")
    mp2 = _create_master_profile(db, u_m2["id"], rating_avg=4.5, rating_count=20)
    _add_service(db, mp2.id, santexnik_cat.id)

    h_c, u_c = signup("customer", "+998901000031", "Mijoz")
    r_order = client.post(
        ORDERS_URL,
        json={
            "category_id": santexnik_cat.id,
            "description": "Kran oqyapti",
            "city": "Toshkent",
            "district": "Chilonzor",
            "address": "Ko'cha 6",
            "selection_mode": "automatic",
        },
        headers=h_c,
    )
    order_id = r_order.json()["id"]

    # Dastlab eng yuqori usta (mp1) taklif olgan
    r1 = client.get(f"{ORDERS_URL}/{order_id}", headers=h_c)
    offers = r1.json()["offers"]
    assert len(offers) == 1
    assert offers[0]["master_id"] == mp1.id

    # Usta 1 rad etadi
    r_rej = client.post(f"{ORDERS_URL}/{order_id}/reject", headers=h_m1)
    assert r_rej.status_code == 200
    assert r_rej.json()["next_master_offered"] is True

    # Endi navbatdagi usta (mp2) taklif olgan, mp1 esa rad etilgan holatda
    r2 = client.get(f"{ORDERS_URL}/{order_id}", headers=h_c)
    all_offers = r2.json()["offers"]
    assert len(all_offers) == 2
    statuses = {o["master_id"]: o["status"] for o in all_offers}
    assert statuses[mp1.id] == "rejected"
    assert statuses[mp2.id] == "pending"

    # Usta 2 ham rad etadi -> hech kim qolmaydi, buyurtma searching holatida qoladi
    r_rej2 = client.post(f"{ORDERS_URL}/{order_id}/reject", headers=h_m2)
    assert r_rej2.status_code == 200
    assert r_rej2.json()["next_master_offered"] is False

    r3 = client.get(f"{ORDERS_URL}/{order_id}", headers=h_c)
    assert r3.json()["status"] == "searching"


def test_reject_in_manual_mode_just_marks_offer(client, db, signup, santexnik_cat):
    """Manual rejimda usta rad etsa yangi usta avtomatik tanlanmaydi."""
    h_m, u_m = signup("master", "+998902000033", "Usta")
    mp = _create_master_profile(db, u_m["id"])
    _add_service(db, mp.id, santexnik_cat.id)

    h_c, u_c = signup("customer", "+998901000032", "Mijoz")
    r_order = client.post(
        ORDERS_URL,
        json={
            "category_id": santexnik_cat.id,
            "description": "Manual ish",
            "city": "Toshkent",
            "district": "Chilonzor",
            "address": "Ko'cha 7",
            "selection_mode": "manual",
        },
        headers=h_c,
    )
    order_id = r_order.json()["id"]
    client.post(f"{ORDERS_URL}/{order_id}/select-master", json={"master_id": mp.id}, headers=h_c)

    # Usta rad etadi
    r_rej = client.post(f"{ORDERS_URL}/{order_id}/reject", headers=h_m)
    assert r_rej.status_code == 200
    assert r_rej.json()["next_master_offered"] is False

    r_get = client.get(f"{ORDERS_URL}/{order_id}", headers=h_c)
    assert r_get.json()["offers"][0]["status"] == "rejected"


# ============================================================================
# 5. GET /masters/me/orders
# ============================================================================


def test_get_master_me_orders(client, db, signup, santexnik_cat):
    """GET /masters/me/orders: pending takliflarda manzil yashirilgan,
    active buyurtmalarda manzil va mijoz ismi bor, boshqa ustaning narsalari yo'q."""
    h_m1, u_m1 = signup("master", "+998902000041", "Usta 1")
    mp1 = _create_master_profile(db, u_m1["id"])
    _add_service(db, mp1.id, santexnik_cat.id)

    h_m2, u_m2 = signup("master", "+998902000042", "Usta 2")
    mp2 = _create_master_profile(db, u_m2["id"])
    _add_service(db, mp2.id, santexnik_cat.id)

    h_c, u_c = signup("customer", "+998901000041", "Mijoz Karim")

    # Buyurtma 1: Usta 1 ga pending taklif
    r1 = client.post(
        ORDERS_URL,
        json={
            "category_id": santexnik_cat.id,
            "description": "Kutilayotgan taklif",
            "city": "Toshkent",
            "district": "Chilonzor",
            "address": "MAXFIY MANZIL 123",
            "selection_mode": "manual",
        },
        headers=h_c,
    )
    oid1 = r1.json()["id"]
    client.post(f"{ORDERS_URL}/{oid1}/select-master", json={"master_id": mp1.id}, headers=h_c)

    # Buyurtma 2: Usta 1 ga biriktirilgan (active)
    r2 = client.post(
        ORDERS_URL,
        json={
            "category_id": santexnik_cat.id,
            "description": "Faol buyurtma",
            "city": "Toshkent",
            "district": "Chilonzor",
            "address": "OCHIQ MANZIL 456",
            "selection_mode": "manual",
        },
        headers=h_c,
    )
    oid2 = r2.json()["id"]
    client.post(f"{ORDERS_URL}/{oid2}/select-master", json={"master_id": mp1.id}, headers=h_c)
    client.post(f"{ORDERS_URL}/{oid2}/accept", headers=h_m1)

    # Buyurtma 3: Usta 2 ning buyurtmasi (Usta 1 ga tegishli emas)
    r3 = client.post(
        ORDERS_URL,
        json={
            "category_id": santexnik_cat.id,
            "description": "Usta 2 ning ishi",
            "city": "Toshkent",
            "district": "Chilonzor",
            "address": "Boshqa manzil",
            "selection_mode": "manual",
        },
        headers=h_c,
    )
    oid3 = r3.json()["id"]
    client.post(f"{ORDERS_URL}/{oid3}/select-master", json={"master_id": mp2.id}, headers=h_c)

    # Usta 1 o'z buyurtmalarini so'raydi
    r = client.get(f"{MASTERS_URL}/me/orders", headers=h_m1)
    assert r.status_code == 200
    data = r.json()

    # Pending offers
    pending = data["pending_offers"]
    assert len(pending) == 1
    assert pending[0]["order_id"] == oid1
    assert pending[0]["description"] == "Kutilayotgan taklif"
    # MAXFIY MANZIL yo'qligini tekshirish
    assert "address" not in pending[0]
    assert "MAXFIY MANZIL" not in str(pending[0])

    # Active orders
    active = data["active_orders"]
    assert len(active) == 1
    assert active[0]["id"] == oid2
    assert active[0]["description"] == "Faol buyurtma"
    assert active[0]["address"] == "OCHIQ MANZIL 456"
    assert active[0]["customer_name"] == "Mijoz Karim"

    # Usta 2 ning buyurtmasi (oid3) Usta 1 da umuman yo'q
    all_ids = [p["order_id"] for p in pending] + [a["id"] for a in active]
    assert oid3 not in all_ids


def test_acceptance_flow_automatic_and_manual(client, db, signup, santexnik_cat):
    """Qabul qilish (Acceptance) ssenariysi:
    1. Avtomatik rejim: mijoz Toshkent/Chilonzorda santexnik buyurtmasi beradi.
       Demo ustalardan biri (Aziz) master-dashboard orqali ko'radi, qabul qiladi.
       Mijoz buyurtmalarida ustaning ismini ko'radi.
    2. Manual rejim: mijoz usta tanlaydi, usta qabul qiladi."""
    h_aziz, u_aziz = signup("master", "+998902222221", "Aziz Karimov")
    mp_aziz = _create_master_profile(db, u_aziz["id"], city="Toshkent", district="Chilonzor")
    _add_service(db, mp_aziz.id, santexnik_cat.id)

    h_cust, u_cust = signup("customer", "+998901111111", "Demo Mijoz")

    # 1. Avtomatik buyurtma
    r_auto = client.post(
        ORDERS_URL,
        json={
            "category_id": santexnik_cat.id,
            "description": "Kran suv oqyapti",
            "city": "Toshkent",
            "district": "Chilonzor",
            "address": "Chilonzor 9-mavze",
            "selection_mode": "automatic",
        },
        headers=h_cust,
    )
    assert r_auto.status_code == 201
    auto_id = r_auto.json()["id"]

    # Aziz taklifni ko'radi
    r_aziz_orders = client.get(f"{MASTERS_URL}/me/orders", headers=h_aziz)
    assert r_aziz_orders.status_code == 200
    pending_offers = r_aziz_orders.json()["pending_offers"]
    assert any(p["order_id"] == auto_id for p in pending_offers)

    # Aziz qabul qiladi
    r_acc = client.post(f"{ORDERS_URL}/{auto_id}/accept", headers=h_aziz)
    assert r_acc.status_code == 200

    # Mijoz Aziz nomini ko'radi
    r_check = client.get(f"{ORDERS_URL}/{auto_id}", headers=h_cust)
    assert r_check.status_code == 200
    assert r_check.json()["status"] == "assigned"
    assert r_check.json()["master_name"] == "Aziz Karimov"

    # 2. Qo'lda (Manual) buyurtma
    r_manual = client.post(
        ORDERS_URL,
        json={
            "category_id": santexnik_cat.id,
            "description": "Vanna almashtirish",
            "city": "Toshkent",
            "district": "Chilonzor",
            "address": "Chilonzor 10-mavze",
            "selection_mode": "manual",
        },
        headers=h_cust,
    )
    assert r_manual.status_code == 201
    man_id = r_manual.json()["id"]

    # Mijoz Azizni tanlaydi
    r_sel = client.post(f"{ORDERS_URL}/{man_id}/select-master", json={"master_id": mp_aziz.id}, headers=h_cust)
    assert r_sel.status_code == 200

    # Aziz rad etadi
    r_rej = client.post(f"{ORDERS_URL}/{man_id}/reject", headers=h_aziz)
    assert r_rej.status_code == 200

    r_man_check = client.get(f"{ORDERS_URL}/{man_id}", headers=h_cust)
    assert r_man_check.json()["offers"][0]["status"] == "rejected"

