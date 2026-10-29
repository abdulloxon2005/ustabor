"""Sevimli ustalar: qo'shish, o'chirish, ro'yxat."""

from app import models
from app.models.enums import PricingType, Role

FAVORITES = "/api/v1/masters/favorites"


def _make_master(db, phone, approved=True):
    user = models.User(
        phone=phone, password_hash="x", full_name="Usta " + phone[-4:], role=Role.MASTER
    )
    db.add(user)
    db.flush()
    profile = models.MasterProfile(
        user_id=user.id,
        city="Toshkent",
        district="Chilonzor",
        is_approved=approved,
        is_available=True,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def test_add_and_list_favorite(client, db, signup):
    cust_headers, _ = signup(role="customer")
    master = _make_master(db, "+998907770001")

    r_add = client.post(f"/api/v1/masters/{master.id}/favorite", headers=cust_headers)
    assert r_add.status_code == 201
    assert r_add.json()["is_favorited"] is True

    r_list = client.get(FAVORITES, headers=cust_headers)
    assert r_list.status_code == 200
    assert len(r_list.json()) == 1
    assert r_list.json()[0]["id"] == master.id


def test_add_favorite_idempotent(client, db, signup):
    cust_headers, _ = signup(role="customer")
    master = _make_master(db, "+998907770002")

    assert client.post(f"/api/v1/masters/{master.id}/favorite", headers=cust_headers).status_code == 201
    assert client.post(f"/api/v1/masters/{master.id}/favorite", headers=cust_headers).status_code == 201

    r_list = client.get(FAVORITES, headers=cust_headers)
    assert len(r_list.json()) == 1


def test_remove_favorite(client, db, signup):
    cust_headers, _ = signup(role="customer")
    master = _make_master(db, "+998907770003")
    client.post(f"/api/v1/masters/{master.id}/favorite", headers=cust_headers)

    r_remove = client.delete(f"/api/v1/masters/{master.id}/favorite", headers=cust_headers)
    assert r_remove.status_code == 200
    assert r_remove.json()["is_favorited"] is False

    r_list = client.get(FAVORITES, headers=cust_headers)
    assert r_list.json() == []


def test_remove_favorite_idempotent_when_not_favorited(client, db, signup):
    cust_headers, _ = signup(role="customer")
    master = _make_master(db, "+998907770004")

    r = client.delete(f"/api/v1/masters/{master.id}/favorite", headers=cust_headers)
    assert r.status_code == 200


def test_favorites_scoped_per_customer(client, db, signup):
    cust_a_headers, _ = signup(role="customer", phone="+998901111001")
    cust_b_headers, _ = signup(role="customer", phone="+998901111002")
    master = _make_master(db, "+998907770005")

    client.post(f"/api/v1/masters/{master.id}/favorite", headers=cust_a_headers)

    assert len(client.get(FAVORITES, headers=cust_a_headers).json()) == 1
    assert len(client.get(FAVORITES, headers=cust_b_headers).json()) == 0


def test_favorite_nonexistent_master_404(client, db, signup):
    cust_headers, _ = signup(role="customer")
    r = client.post("/api/v1/masters/999999/favorite", headers=cust_headers)
    assert r.status_code == 404


def test_unapproved_master_excluded_from_favorites_list(client, db, signup):
    cust_headers, _ = signup(role="customer")
    master = _make_master(db, "+998907770006", approved=False)

    r_add = client.post(f"/api/v1/masters/{master.id}/favorite", headers=cust_headers)
    assert r_add.status_code == 201

    r_list = client.get(FAVORITES, headers=cust_headers)
    assert r_list.json() == []


def test_master_cannot_favorite(client, db, signup):
    master_headers, _ = signup(role="master")
    other_master = _make_master(db, "+998907770007")

    r = client.post(f"/api/v1/masters/{other_master.id}/favorite", headers=master_headers)
    assert r.status_code == 403


def test_favorites_require_auth(client):
    assert client.get(FAVORITES).status_code == 401
