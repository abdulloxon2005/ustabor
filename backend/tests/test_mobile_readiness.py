from datetime import datetime, timezone

from sqlalchemy import select

from app.core.security import create_access_token
from app.models import Category, MasterProfile, MasterService, Order, OrderOffer, User
from app.models.enums import OfferStatus, OrderStatus, PricingType, Role, SelectionMode


def _add_master(db, phone, city="Toshkent", lat=41.3, lon=69.2):
    user = User(phone=phone, password_hash="x", full_name=phone, role=Role.MASTER)
    db.add(user)
    db.flush()
    category = db.scalar(select(Category))
    profile = MasterProfile(
        user_id=user.id, city=city, district="Chilonzor", is_approved=True,
        is_available=True, latitude=lat, longitude=lon,
        location_sharing_enabled=True,
        location_updated_at=datetime.now(timezone.utc),
    )
    db.add(profile)
    db.flush()
    db.add(MasterService(master_id=profile.id, category_id=category.id,
                         pricing_type=PricingType.QUOTE, base_price=None))
    db.commit()
    return user, profile


def test_location_is_opt_in_private_and_nearby_returns_distance(client, db, signup, auth_header, make_category):
    make_category()
    headers, user = signup(role="master", phone="+998901234567")
    create = client.post("/api/v1/masters/profile", json={"city": "Toshkent", "district": "Chilonzor"}, headers=headers)
    assert create.status_code == 201
    profile_id = create.json()["id"]
    profile = db.get(MasterProfile, profile_id)
    profile.is_approved = True
    db.commit()
    updated = client.post("/api/v1/masters/me/location", json={
        "sharing_enabled": True, "latitude": 41.3, "longitude": 69.2,
    }, headers=headers)
    assert updated.status_code == 200
    assert updated.json()["location_sharing_enabled"] is True
    assert client.get("/api/v1/masters/" + str(profile_id)).json()["latitude"] is None

    # Customers see proximity only; exact coordinates stay private.
    customer_headers, _ = signup(role="customer", phone="+998909876543")
    nearby = client.get("/api/v1/masters/nearby?latitude=41.301&longitude=69.2", headers=customer_headers)
    assert nearby.status_code == 200
    assert nearby.json()[0]["id"] == profile_id
    assert nearby.json()[0]["distance_km"] > 0


def test_location_requires_active_master_and_can_be_revoked(client, db, signup, make_category):
    make_category()
    headers, _ = signup(role="master", phone="+998901234568")
    client.post("/api/v1/masters/profile", json={"city": "Toshkent", "district": "Chilonzor"}, headers=headers)
    r = client.post("/api/v1/masters/me/location", json={
        "sharing_enabled": True, "latitude": 41.3, "longitude": 69.2,
    }, headers=headers)
    assert r.status_code == 200
    r = client.post("/api/v1/masters/me/location", json={"sharing_enabled": False}, headers=headers)
    assert r.status_code == 200
    assert r.json()["latitude"] is None
    assert r.json()["location_sharing_enabled"] is False


def test_dispatch_expands_radius_and_excludes_rejected_masters(client, db, signup, make_category):
    category = make_category()
    customer_headers, customer = signup(role="customer", phone="+998901111111")
    _, near = _add_master(db, "+998902222221", lat=41.30, lon=69.20)
    _, farther = _add_master(db, "+998902222222", lat=41.37, lon=69.20)

    created = client.post("/api/v1/orders", json={
        "category_id": category.id, "description": "Quvurdan suv oqmoqda",
        "city": "Toshkent", "district": "Chilonzor", "address": "Test manzil",
        "selection_mode": "automatic", "latitude": 41.301, "longitude": 69.20,
    }, headers=customer_headers)
    assert created.status_code == 201, created.text
    order_id = created.json()["id"]
    assert [o["master_id"] for o in created.json()["offers"]] == [near.id]

    near_headers = {"Authorization": f"Bearer {create_access_token(near.user_id)}"}
    rejected = client.post(f"/api/v1/orders/{order_id}/reject", headers=near_headers)
    assert rejected.status_code == 200
    offer = db.scalar(select(OrderOffer).where(OrderOffer.order_id == order_id,
                                               OrderOffer.master_id == farther.id))
    assert offer is not None and offer.status == OfferStatus.PENDING

    status = client.get(f"/api/v1/orders/{order_id}/dispatch-status", headers=customer_headers)
    assert status.status_code == 200
    assert status.json()["status"] == "waiting"
    assert status.json()["rejected_offers"] == 1


def test_dispatch_does_not_reassign_closed_order(client, db, signup, make_category):
    category = make_category()
    headers, customer = signup(role="customer", phone="+998901111112")
    order = Order(customer_id=customer["id"], category_id=category.id,
                  description="Yopiq buyurtma test", city="Toshkent", district="Tuman",
                  address="Manzil", status=OrderStatus.COMPLETED,
                  selection_mode=SelectionMode.AUTOMATIC, dispatch_radius_km=0)
    db.add(order)
    db.commit()
    response = client.post(f"/api/v1/orders/{order.id}/dispatch", headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "completed"


def test_admin_commission_settings_are_saved_and_old_order_rate_is_snapshotted(client, db, admin_headers, signup, make_category):
    category = make_category()
    headers, customer = signup(role="customer", phone="+998901111113")
    old = Order(customer_id=customer["id"], category_id=category.id,
                description="Old commission snapshot", city="Toshkent", district="Tuman",
                address="Manzil", status=OrderStatus.SEARCHING,
                selection_mode=SelectionMode.MANUAL, commission_rate=10)
    db.add(old)
    db.commit()

    updated = client.patch("/api/v1/admin/settings/commission", headers=admin_headers,
                           json={"enabled": False, "rate": 7})
    assert updated.status_code == 200, updated.text
    assert updated.json()["enabled"] is False
    assert client.get("/api/v1/admin/settings/commission", headers=admin_headers).json()["rate"] == 7
    assert db.get(Order, old.id).commission_rate == 10


def test_admin_analytics_endpoints_and_non_admin_access(client, admin_headers, signup, make_category):
    make_category()
    response = client.get("/api/v1/admin/analytics/overview?limit=5", headers=admin_headers)
    assert response.status_code == 200, response.text
    assert "status_counts" in response.json()
    assert client.get("/api/v1/admin/analytics/categories", headers=admin_headers).status_code == 200
    assert client.get("/api/v1/admin/analytics/geo", headers=admin_headers).status_code == 200
    customer_headers, _ = signup(role="customer", phone="+998901111114")
    assert client.get("/api/v1/admin/analytics/overview", headers=customer_headers).status_code == 403


def test_device_token_and_push_failure_do_not_break_notification(client, db, signup, make_category, monkeypatch):
    make_category()
    headers, user = signup(role="master", phone="+998901234569")
    client.post("/api/v1/masters/profile", json={"city": "Toshkent", "district": "Chilonzor"}, headers=headers)
    response = client.post("/api/v1/masters/me/device-token", headers=headers,
                           json={"token": "a" * 80, "platform": "android"})
    assert response.status_code == 200
    assert response.json()["registered"] is True

    from app.services import notify, push
    def fail_push(*args, **kwargs):
        raise RuntimeError("simulated push transport failure")
    monkeypatch.setattr(push, "send_push", fail_push)
    notify.notify_user(db, user["id"], "test", "Sarlavha", "Matn")
    db.commit()


def test_chat_reports_are_private_and_admin_moderation_is_audited(client, db, admin_headers, signup, make_category):
    make_category()
    customer_headers, customer = signup(role="customer", phone="+998901111115")
    master_user, master = _add_master(db, "+998902222223")
    order = Order(customer_id=customer["id"], category_id=db.scalar(select(Category.id)),
                  master_id=master.id, description="Chat report test", city="Toshkent",
                  district="Chilonzor", address="Manzil", status=OrderStatus.ASSIGNED,
                  selection_mode=SelectionMode.MANUAL)
    db.add(order)
    db.flush()
    from app.models import OrderMessage
    message = OrderMessage(order_id=order.id, sender_id=master_user.id, body="Nomaqbul xabar")
    db.add(message)
    db.commit()

    reported = client.post(f"/api/v1/orders/{order.id}/messages/{message.id}/report",
                           headers=customer_headers, json={"reason": "Shubhali xabar matni"})
    assert reported.status_code == 201, reported.text
    assert client.get(f"/api/v1/admin/chats/reported", headers=admin_headers).json()[0]["message_body"] == "Nomaqbul xabar"
    moderated = client.post(f"/api/v1/admin/chats/{order.id}/moderation", headers=admin_headers,
                            json={"message_id": message.id, "hide": True, "note": "Tekshirildi"})
    assert moderated.status_code == 200, moderated.text
    assert client.get(f"/api/v1/orders/{order.id}/messages", headers=customer_headers).json() == []
    from app.models import AdminAuditLog
    assert db.scalar(select(AdminAuditLog).where(AdminAuditLog.action == "moderate_chat_message")) is not None
