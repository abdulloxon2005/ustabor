"""To'liq buyurtma jarayoni (Demo ssenariy) - HTTP orqali:
Mijoz ro'yxatdan o'tadi va manual santexnik buyurtma yaratadi ->
ustani tanlaydi -> usta qabul qiladi -> usta 200 000 so'm taklif qiladi ->
mijoz tasdiqlaydi -> usta ishni boshlaydi -> usta ishni yakunlaydi.
"""

from sqlalchemy import select

from app import models
from app.models.enums import OrderStatus, PaymentMethod, PaymentStatus, PricingType


def _create_master(db, user_id, cat_id, pricing_type=PricingType.QUOTE, base_price=None):
    mp = models.MasterProfile(
        user_id=user_id,
        bio="Tajribali usta",
        city="Toshkent",
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


def test_full_demo_scenario(client, db, signup, make_category):
    cat = make_category("Santexnik", "santexnik")

    # 1. Mijoz ro'yxatdan o'tadi
    h_c, u_c = signup("customer", "+998901111111", "Demo Mijoz")

    # 2. Usta ro'yxatdan o'tadi va profilini yaratadi (quote turidagi)
    h_m, u_m = signup("master", "+998902222223", "Bobur Usta")
    mp = _create_master(db, u_m["id"], cat.id, pricing_type=PricingType.QUOTE, base_price=None)

    # 3. Mijoz manual santexnik buyurtma yaratadi
    r_create = client.post(
        "/api/v1/orders",
        json={
            "category_id": cat.id,
            "description": "Quvurni ta'mirlash va kran o'rnatish",
            "city": "Toshkent",
            "district": "Chilonzor",
            "address": "Muqimiy ko'chasi 45",
            "selection_mode": "manual",
        },
        headers=h_c,
    )
    assert r_create.status_code == 201, r_create.text
    order_id = r_create.json()["id"]

    # 4. Mijoz ustani tanlaydi
    r_select = client.post(
        f"/api/v1/orders/{order_id}/select-master",
        json={"master_id": mp.id},
        headers=h_c,
    )
    assert r_select.status_code == 200, r_select.text

    # 5. Usta taklifni qabul qiladi
    r_accept = client.post(f"/api/v1/orders/{order_id}/accept", headers=h_m)
    assert r_accept.status_code == 200, r_accept.text

    # 6. Usta 200 000 so'm narx taklif qiladi
    r_quote = client.post(
        f"/api/v1/orders/{order_id}/quotes",
        json={"price": 200_000, "note": "Kran va ulanish narxi bilan"},
        headers=h_m,
    )
    assert r_quote.status_code == 201, r_quote.text
    quote_data = r_quote.json()
    assert quote_data["price"] == 200_000
    assert quote_data["status"] == "proposed"
    quote_id = quote_data["id"]

    # Ustaning /masters/me/orders ro'yxatida active order va latest_quote ko'rinadi
    r_master_orders = client.get("/api/v1/masters/me/orders", headers=h_m)
    assert r_master_orders.status_code == 200
    mo_data = r_master_orders.json()
    assert len(mo_data["active_orders"]) == 1
    assert mo_data["active_orders"][0]["latest_quote"]["price"] == 200_000

    # 7. Mijoz narx taklifini qabul qiladi
    r_quote_accept = client.post(
        f"/api/v1/orders/{order_id}/quotes/{quote_id}/accept",
        headers=h_c,
    )
    assert r_quote_accept.status_code == 200, r_quote_accept.text
    assert r_quote_accept.json()["agreed_price"] == 200_000

    # 8. Usta ishni boshlaydi
    r_start = client.post(f"/api/v1/orders/{order_id}/start", headers=h_m)
    assert r_start.status_code == 200, r_start.text
    assert r_start.json()["status"] == "in_progress"

    # 9. Usta ishni yakunlaydi
    r_complete = client.post(f"/api/v1/orders/{order_id}/complete", headers=h_m)
    assert r_complete.status_code == 200, r_complete.text
    comp_data = r_complete.json()
    assert comp_data["price"] == 200_000
    assert comp_data["commission_rate"] == 10
    assert comp_data["commission_amount"] == 20_000
    assert comp_data["net_amount"] == 180_000
    assert comp_data["net"] == 180_000

    # 10. Bazadagi buyurtma ma'lumotlarini tekshirish
    db.expire_all()
    order = db.get(models.Order, order_id)
    assert order.status == OrderStatus.COMPLETED
    assert order.agreed_price == 200_000
    assert order.commission_rate == 10
    assert order.commission_amount == 20_000
    assert (order.agreed_price - order.commission_amount) == 180_000

    # To'lov tekshiruvi: bitta CASH to'lov 200_000
    payments = db.scalars(
        select(models.Payment).where(models.Payment.order_id == order_id)
    ).all()
    assert len(payments) == 1
    payment = payments[0]
    assert payment.method == PaymentMethod.CASH
    assert payment.amount == 200_000
    assert payment.status == PaymentStatus.PAID

    # Holat tarixi tekshiruvi: searching -> assigned -> in_progress -> completed
    histories = db.scalars(
        select(models.OrderStatusHistory)
        .where(models.OrderStatusHistory.order_id == order_id)
        .order_by(models.OrderStatusHistory.id)
    ).all()
    statuses = [h.to_status for h in histories]
    assert statuses == [
        OrderStatus.SEARCHING,
        OrderStatus.ASSIGNED,
        OrderStatus.IN_PROGRESS,
        OrderStatus.COMPLETED,
    ]

    # 11. Ustaning /masters/me/earnings tekshiruvi
    r_earnings = client.get("/api/v1/masters/me/earnings", headers=h_m)
    assert r_earnings.status_code == 200, r_earnings.text
    earn = r_earnings.json()
    assert earn["completed_count"] == 1
    assert earn["gross_total"] == 200_000
    assert earn["commission_total"] == 20_000
    assert earn["net_total"] == 180_000
    assert len(earn["orders"]) == 1
    assert earn["orders"][0]["id"] == order_id
    assert earn["orders"][0]["agreed_price"] == 200_000
    assert earn["orders"][0]["commission_amount"] == 20_000
    assert earn["orders"][0]["net"] == 180_000

    # 12. Mijoz buyurtmasi tekshiruvi (GET /orders/{id}):
    # Mijoz commission_amount va usta sof daromadini KO'RMASLIGI shart
    r_cust_order = client.get(f"/api/v1/orders/{order_id}", headers=h_c)
    assert r_cust_order.status_code == 200
    co = r_cust_order.json()
    assert "commission_amount" not in co
    assert "net" not in co
    assert "net_amount" not in co
    assert co["agreed_price"] == 200_000
    assert co["final_price"] == 200_000
    assert co["status"] == "completed"
    assert len(co["quotes"]) == 1
    assert co["quotes"][0]["price"] == 200_000
