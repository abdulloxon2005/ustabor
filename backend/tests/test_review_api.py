"""HTTP API testlar: Sharhlar va reytinglar (Review API)."""

from datetime import datetime

import pytest
from sqlalchemy import select

from app import models
from app.models.enums import OrderStatus, PricingType, Role, SelectionMode
from app.services import matching
from app.services.matching import global_average, rank_masters, score_master
from app.services.order_flow import assign_master, create_order_history, transition


def _create_master(db, user_id: int, cat_id: int, is_approved: bool = True) -> models.MasterProfile:
    mp = models.MasterProfile(
        user_id=user_id,
        bio="Tajribali usta",
        city="Toshkent",
        district="Chilonzor",
        is_approved=is_approved,
        is_available=True,
    )
    db.add(mp)
    db.flush()
    ms = models.MasterService(
        master_id=mp.id,
        category_id=cat_id,
        pricing_type=PricingType.FIXED,
        base_price=100_000,
    )
    db.add(ms)
    db.commit()
    db.refresh(mp)
    return mp


def _create_completed_order(client, db, cust_headers, master_profile, cat_id) -> int:
    # Buyurtma yaratamiz va to'g'ridan-to'g'ri completed holatiga keltiramiz
    user = db.scalar(select(models.User).where(models.User.id == master_profile.user_id))
    r = client.post(
        "/api/v1/orders",
        json={
            "category_id": cat_id,
            "description": "Santexnika ta'mirlash ishlari",
            "city": "Toshkent",
            "district": "Chilonzor",
            "address": "Navoiy ko'chasi 10",
            "selection_mode": "manual",
        },
        headers=cust_headers,
    )
    assert r.status_code == 201
    order_id = r.json()["id"]

    order = db.get(models.Order, order_id)
    assign_master(db, order.id, master_profile.id, actor=user)
    order.agreed_price = 100_000
    transition(db, order, OrderStatus.IN_PROGRESS, actor=user)
    transition(db, order, OrderStatus.COMPLETED, actor=user)
    db.commit()
    return order_id


def assert_no_forbidden_keys(obj, forbidden={"commission_amount", "net", "net_amount"}):
    if isinstance(obj, dict):
        for k, v in obj.items():
            assert k not in forbidden, f"Topilgan taqiqlangan maydon: {k}"
            assert_no_forbidden_keys(v, forbidden)
    elif isinstance(obj, list):
        for item in obj:
            assert_no_forbidden_keys(item, forbidden)


def test_review_completed_order_happy_path(client, db, signup, make_category):
    cat = make_category("Santexnik", "santexnik")
    h_c, u_c = signup("customer", "+998901110001", "Ali Valiyev")
    h_m, u_m = signup("master", "+998902220001", "Vali Usta")
    mp = _create_master(db, u_m["id"], cat.id)

    order_id = _create_completed_order(client, db, h_c, mp, cat.id)

    # Buyurtma egasi sharh qoldiradi
    r_rev = client.post(
        f"/api/v1/orders/{order_id}/review",
        json={"rating": 5, "comment": "Ajoyib ish, rahmat!"},
        headers=h_c,
    )
    assert r_rev.status_code == 201, r_rev.text
    data = r_rev.json()
    assert data["rating"] == 5
    assert data["comment"] == "Ajoyib ish, rahmat!"
    assert "created_at" in data

    # Ustaning reytingi yangilandi
    db.expire_all()
    mp_db = db.get(models.MasterProfile, mp.id)
    assert mp_db.rating_count == 1
    assert mp_db.rating_avg == 5.0

    # Mijoz buyurtma tafsilotini ko'radi (GET /orders/{id})
    r_order = client.get(f"/api/v1/orders/{order_id}", headers=h_c)
    assert r_order.status_code == 200
    order_data = r_order.json()
    assert order_data["review"] is not None
    assert order_data["review"]["rating"] == 5
    assert order_data["review"]["comment"] == "Ajoyib ish, rahmat!"
    assert order_data["can_review"] is False

    # Mijoz ko'rinishida hech qanday komissiya yoki net summasi yo'q
    assert_no_forbidden_keys(order_data)


def test_review_before_completion_409(client, db, signup, make_category):
    cat = make_category("Santexnik", "santexnik_bc")
    h_c, u_c = signup("customer", "+998901110002", "Mijoz 2")
    h_m, u_m = signup("master", "+998902220002", "Usta 2")
    mp = _create_master(db, u_m["id"], cat.id)

    r = client.post(
        "/api/v1/orders",
        json={
            "category_id": cat.id,
            "description": "Hali yakunlanmagan buyurtma",
            "city": "Toshkent",
            "district": "Chilonzor",
            "address": "Navoiy 11",
            "selection_mode": "manual",
        },
        headers=h_c,
    )
    assert r.status_code == 201
    order_id = r.json()["id"]

    # Searching holatida sharh qoldirish -> 409
    r_rev = client.post(
        f"/api/v1/orders/{order_id}/review",
        json={"rating": 5, "comment": "Erta sharh"},
        headers=h_c,
    )
    assert r_rev.status_code == 409


def test_review_second_review_409(client, db, signup, make_category):
    cat = make_category("Santexnik", "santexnik_sr")
    h_c, u_c = signup("customer", "+998901110003", "Mijoz 3")
    h_m, u_m = signup("master", "+998902220003", "Usta 3")
    mp = _create_master(db, u_m["id"], cat.id)

    order_id = _create_completed_order(client, db, h_c, mp, cat.id)

    # Birinchi sharh -> 201
    r1 = client.post(
        f"/api/v1/orders/{order_id}/review",
        json={"rating": 5, "comment": "Birinchi"},
        headers=h_c,
    )
    assert r1.status_code == 201

    # Ikkinchi sharh -> 409
    r2 = client.post(
        f"/api/v1/orders/{order_id}/review",
        json={"rating": 4, "comment": "Ikkinchi"},
        headers=h_c,
    )
    assert r2.status_code == 409


def test_review_another_customer_404(client, db, signup, make_category):
    cat = make_category("Santexnik", "santexnik_ac")
    h_c1, u_c1 = signup("customer", "+998901110004", "Mijoz Egasi")
    h_c2, u_c2 = signup("customer", "+998901110005", "Begona Mijoz")
    h_m, u_m = signup("master", "+998902220004", "Usta 4")
    mp = _create_master(db, u_m["id"], cat.id)

    order_id = _create_completed_order(client, db, h_c1, mp, cat.id)

    # Begona mijoz sharh qoldirmoqchi bo'lsa -> 404
    r_rev = client.post(
        f"/api/v1/orders/{order_id}/review",
        json={"rating": 5, "comment": "Begonadan"},
        headers=h_c2,
    )
    assert r_rev.status_code == 404


def test_review_master_or_anonymous_forbidden(client, db, signup, make_category):
    cat = make_category("Santexnik", "santexnik_ma")
    h_c, u_c = signup("customer", "+998901110006", "Mijoz 6")
    h_m, u_m = signup("master", "+998902220005", "Usta 5")
    mp = _create_master(db, u_m["id"], cat.id)

    order_id = _create_completed_order(client, db, h_c, mp, cat.id)

    # Anonim -> 401
    r_anon = client.post(
        f"/api/v1/orders/{order_id}/review",
        json={"rating": 5, "comment": "Anonim"},
    )
    assert r_anon.status_code == 401

    # Usta -> 403
    r_mast = client.post(
        f"/api/v1/orders/{order_id}/review",
        json={"rating": 5, "comment": "Usta nomidan"},
        headers=h_m,
    )
    assert r_mast.status_code == 403


def test_review_validation_errors(client, db, signup, make_category):
    cat = make_category("Santexnik", "santexnik_ve")
    h_c, u_c = signup("customer", "+998901110007", "Mijoz 7")
    h_m, u_m = signup("master", "+998902220006", "Usta 6")
    mp = _create_master(db, u_m["id"], cat.id)

    order_id = _create_completed_order(client, db, h_c, mp, cat.id)

    # rating = 0 -> 422
    r0 = client.post(
        f"/api/v1/orders/{order_id}/review",
        json={"rating": 0},
        headers=h_c,
    )
    assert r0.status_code == 422

    # rating = 6 -> 422
    r6 = client.post(
        f"/api/v1/orders/{order_id}/review",
        json={"rating": 6},
        headers=h_c,
    )
    assert r6.status_code == 422

    # comment > 1000 belgisi -> 422
    r_long = client.post(
        f"/api/v1/orders/{order_id}/review",
        json={"rating": 5, "comment": "a" * 1001},
        headers=h_c,
    )
    assert r_long.status_code == 422


def test_review_protected_fields_ignored(client, db, signup, make_category):
    cat = make_category("Santexnik", "santexnik_pf")
    h_c, u_c = signup("customer", "+998901110008", "Mijoz 8")
    h_m, u_m = signup("master", "+998902220007", "Usta 7")
    mp = _create_master(db, u_m["id"], cat.id)

    order_id = _create_completed_order(client, db, h_c, mp, cat.id)

    # Himoyalangan maydonlar bilan yuborish
    r = client.post(
        f"/api/v1/orders/{order_id}/review",
        json={
            "rating": 5,
            "comment": "Toza ish",
            "status": "searching",
            "master_id": 9999,
            "customer_id": 9999,
            "agreed_price": 500_000,
            "role": "admin",
        },
        headers=h_c,
    )
    assert r.status_code == 201


def test_get_master_reviews_public_and_no_customer_identity(client, db, signup, make_category):
    cat = make_category("Santexnik", "santexnik_pub")
    h_c, u_c = signup("customer", "+998901110009", "Javohir Toshmatov")
    h_m, u_m = signup("master", "+998902220008", "Sarvar Usta")
    mp = _create_master(db, u_m["id"], cat.id)

    order_id = _create_completed_order(client, db, h_c, mp, cat.id)

    client.post(
        f"/api/v1/orders/{order_id}/review",
        json={"rating": 5, "comment": "Juda sifatli xizmat ko'rsatildi!"},
        headers=h_c,
    )

    # Ommaviy GET /masters/{id}/reviews
    r = client.get(f"/api/v1/masters/{mp.id}/reviews")
    assert r.status_code == 200
    res = r.json()
    assert res["rating_avg"] == 5.0
    assert res["rating_count"] == 1
    assert len(res["reviews"]) == 1

    item = res["reviews"][0]
    assert item["rating"] == 5
    assert item["comment"] == "Juda sifatli xizmat ko'rsatildi!"
    assert item["customer_first_name"] == "Javohir"

    # Mijoz identifikatorlari (telefon, to'liq ism, id) umuman yo'qligini tekshirish
    forbidden_review_keys = {"phone", "customer_phone", "full_name", "customer_full_name", "customer_id", "user_id"}
    for k in forbidden_review_keys:
        assert k not in item, f"Sharh javobida maxfiy kalit mavjud: {k}"


def test_unapproved_or_blocked_master_reviews_404(client, db, signup, make_category):
    cat = make_category("Santexnik", "santexnik_unapp")
    h_m, u_m = signup("master", "+998902220009", "Tasdiqlanmagan Usta")
    mp = _create_master(db, u_m["id"], cat.id, is_approved=False)

    # Tasdiqlanmagan usta sharhlari -> 404
    r1 = client.get(f"/api/v1/masters/{mp.id}/reviews")
    assert r1.status_code == 404

    # Tasdiqlangan lekin bloklangan usta -> 404
    mp.is_approved = True
    user = db.get(models.User, u_m["id"])
    user.is_active = False
    db.commit()

    r2 = client.get(f"/api/v1/masters/{mp.id}/reviews")
    assert r2.status_code == 404


def test_rating_propagation_and_matching(client, db, signup, make_category):
    """Sharhlar qoldirilgach reyting GET /masters va GET /masters/{id} da ko'rinadi,
    va matching xizmati ko'p sharhli 4.8 ustani 1 sharhli 5.0 ustadan yuqori qo'yadi.
    """
    cat = make_category("Santexnik", "santexnik_match")

    # Usta A (ko'p sharh, 4.8)
    h_ma, u_ma = signup("master", "+998902220010", "Tajribali Usta A")
    mp_a = _create_master(db, u_ma["id"], cat.id)
    mp_a.rating_avg = 4.8
    mp_a.rating_count = 50
    db.commit()

    # Usta B (bitta sharh, 5.0)
    h_mb, u_mb = signup("master", "+998902220011", "Yangi Usta B")
    mp_b = _create_master(db, u_mb["id"], cat.id)
    mp_b.rating_avg = 5.0
    mp_b.rating_count = 1
    db.commit()

    # GET /masters da ko'rinishi
    r_list = client.get(f"/api/v1/masters?category_id={cat.id}")
    assert r_list.status_code == 200
    masters = r_list.json()
    m_a_found = next(m for m in masters if m["id"] == mp_a.id)
    m_b_found = next(m for m in masters if m["id"] == mp_b.id)
    assert m_a_found["rating_avg"] == 4.8
    assert m_a_found["rating_count"] == 50
    assert m_b_found["rating_avg"] == 5.0
    assert m_b_found["rating_count"] == 1

    # GET /masters/{id} da ko'rinishi
    r_single = client.get(f"/api/v1/masters/{mp_a.id}")
    assert r_single.status_code == 200
    assert r_single.json()["rating_avg"] == 4.8
    assert r_single.json()["rating_count"] == 50

    # Matching tekshiruvi:
    # 4.8 li ko'p sharhli usta 5.0 li 1 sharhli ustadan yuqori skorni olishi kerak
    # Mijoz va buyurtma
    h_c, u_c = signup("customer", "+998901110010", "Matching Mijoz")
    r_ord = client.post(
        "/api/v1/orders",
        json={
            "category_id": cat.id,
            "description": "Matching uchun test buyurtma",
            "city": "Toshkent",
            "district": "Chilonzor",
            "address": "Qatortol 1",
            "selection_mode": "automatic",
        },
        headers=h_c,
    )
    order_id = r_ord.json()["id"]
    order = db.get(models.Order, order_id)

    g_avg = global_average(db)
    bayes_a = matching.bayes_rating(mp_a.rating_avg, mp_a.rating_count, g_avg)
    bayes_b = matching.bayes_rating(mp_b.rating_avg, mp_b.rating_count, g_avg)
    assert bayes_a > bayes_b, f"4.8 li ko'p sharhli usta Bayes reytingi ({bayes_a}) 5.0 li 1 sharhli ustadan ({bayes_b}) katta bo'lishi kerak"

