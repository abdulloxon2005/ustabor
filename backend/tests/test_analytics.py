"""Admin statistika paneli: kunlik buyurtma/komissiya, top kategoriyalar, yangi foydalanuvchilar."""

from datetime import date

from app.models.enums import PricingType

from tests.test_admin_api import _create_master_profile

ANALYTICS = "/api/v1/admin/analytics"


def test_analytics_default_period_structure(client, db, admin_headers):
    r = client.get(ANALYTICS, headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["period_days"] == 30
    assert len(body["daily"]) == 30
    assert len(body["new_users"]) == 30
    assert body["date_to"] == date.today().isoformat()
    assert isinstance(body["top_categories"], list)


def test_analytics_days_param(client, db, admin_headers):
    r = client.get(ANALYTICS + "?days=7", headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["period_days"] == 7
    assert len(body["daily"]) == 7
    assert len(body["new_users"]) == 7


def test_analytics_days_param_out_of_range_rejected(client, db, admin_headers):
    assert client.get(ANALYTICS + "?days=0", headers=admin_headers).status_code == 422
    assert client.get(ANALYTICS + "?days=366", headers=admin_headers).status_code == 422


def test_analytics_counts_orders_commission_and_top_categories(
    client, db, signup, admin_headers, make_category
):
    cat = make_category("Santexnik", "santexnik_analytics")
    h_c, u_c = signup("customer", "+998901230030", "Mijoz Analitika")
    h_m, u_m = signup("master", "+998901230031", "Usta Analitika")
    mp = _create_master_profile(db, u_m["id"], cat.id, pricing_type=PricingType.QUOTE, base_price=None)

    r_create = client.post(
        "/api/v1/orders",
        json={
            "category_id": cat.id,
            "description": "Nasos almashtirish",
            "city": "Toshkent",
            "district": "Chilonzor",
            "address": "Muqimiy 10",
            "selection_mode": "manual",
        },
        headers=h_c,
    )
    assert r_create.status_code == 201
    order_id = r_create.json()["id"]

    client.post(f"/api/v1/orders/{order_id}/select-master", json={"master_id": mp.id}, headers=h_c)
    client.post(f"/api/v1/orders/{order_id}/accept", headers=h_m)
    r_quote = client.post(
        f"/api/v1/orders/{order_id}/quotes",
        json={"price": 200_000, "note": "Narx"},
        headers=h_m,
    )
    quote_id = r_quote.json()["id"]
    client.post(f"/api/v1/orders/{order_id}/quotes/{quote_id}/accept", headers=h_c)
    client.post(f"/api/v1/orders/{order_id}/start", headers=h_m)
    client.post(f"/api/v1/orders/{order_id}/complete", headers=h_m)

    r = client.get(ANALYTICS, headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total_orders"] >= 1
    assert body["total_completed_orders"] >= 1
    assert body["total_commission"] >= 20_000

    today_key = date.today().isoformat()
    today_entry = next(d for d in body["daily"] if d["date"] == today_key)
    assert today_entry["orders_count"] >= 1
    assert today_entry["completed_count"] >= 1
    assert today_entry["commission_total"] >= 20_000

    cat_entry = next((c for c in body["top_categories"] if c["category_name"] == "Santexnik"), None)
    assert cat_entry is not None
    assert cat_entry["orders_count"] >= 1


def test_analytics_counts_new_users_by_role(client, db, signup, admin_headers):
    signup("customer", "+998901230040", "Mijoz Yangi 1")
    signup("customer", "+998901230041", "Mijoz Yangi 2")
    signup("master", "+998901230042", "Usta Yangi")

    r = client.get(ANALYTICS, headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total_new_users"] >= 3

    today_key = date.today().isoformat()
    today_entry = next(d for d in body["new_users"] if d["date"] == today_key)
    assert today_entry["customers"] >= 2
    assert today_entry["masters"] >= 1


def test_analytics_requires_admin(client, db, signup):
    h_c, _ = signup("customer", "+998901230050", "Mijoz Ruxsat")
    r = client.get(ANALYTICS, headers=h_c)
    assert r.status_code == 403

    r_anon = client.get(ANALYTICS)
    assert r_anon.status_code == 401
