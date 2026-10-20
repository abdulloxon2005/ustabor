import pytest

M = "/api/v1/masters"
PROFILE = {"bio": "Tajribali usta", "city": "Toshkent", "district": "Chilonzor"}


def create_profile(client, headers, **overrides):
    return client.post(f"{M}/profile", json={**PROFILE, **overrides}, headers=headers)


def approve(client, admin_headers, profile_id, value=True):
    r = client.patch(
        f"/api/v1/admin/masters/{profile_id}/approval",
        json={"is_approved": value},
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    return r


@pytest.fixture
def master(client, signup):
    """Profili yaratilgan (tasdiqlanmagan) usta: (headers, profile_id)."""
    headers, _ = signup("master", "+998902222221", "Aziz Karimov")
    r = create_profile(client, headers)
    assert r.status_code == 201
    return headers, r.json()["id"]


def listing(client, **params):
    r = client.get(M, params=params)
    assert r.status_code == 200
    return r.json()


def assert_no_secrets(text: str):
    low = text.lower()
    assert "phone" not in low
    assert "password" not in low
    assert "+998" not in low


# ---------- profil yaratish ----------

def test_create_profile_not_approved_and_hidden(client, master):
    headers, pid = master
    me = client.get(f"{M}/me", headers=headers).json()
    assert me["is_approved"] is False
    assert me["is_available"] is True
    assert me["services"] == []
    assert listing(client) == []


def test_is_approved_in_request_ignored(client, signup):
    headers, _ = signup("master", "+998902222221")
    r = create_profile(client, headers, is_approved=True, is_available=False, rating_avg=5)
    assert r.status_code == 201
    assert r.json()["is_approved"] is False
    assert r.json()["is_available"] is True
    assert r.json()["rating_avg"] == 0
    assert listing(client) == []


def test_second_profile_409(client, master):
    headers, _ = master
    assert create_profile(client, headers).status_code == 409


def test_profile_validation(client, signup):
    headers, _ = signup("master", "+998902222221")
    assert create_profile(client, headers, city="  ").status_code == 422
    assert create_profile(client, headers, district="").status_code == 422
    assert client.post(f"{M}/profile", json={}, headers=headers).status_code == 422


def test_customer_and_anonymous_blocked_from_master_endpoints(client, signup):
    headers, _ = signup("customer", "+998901111111")
    calls = [
        ("post", f"{M}/profile", PROFILE),
        ("get", f"{M}/me", None),
        ("patch", f"{M}/me", {"city": "X"}),
        ("put", f"{M}/me/services", []),
        ("patch", f"{M}/me/availability", {"is_available": False}),
    ]
    for method, url, body in calls:
        kw = {"json": body} if body is not None else {}
        assert getattr(client, method)(url, headers=headers, **kw).status_code == 403, url
        assert getattr(client, method)(url, **kw).status_code == 401, url


def test_master_without_profile_404(client, signup):
    headers, _ = signup("master", "+998902222221")
    assert client.get(f"{M}/me", headers=headers).status_code == 404
    assert client.patch(f"{M}/me/availability", json={"is_available": False}, headers=headers).status_code == 404


def test_patch_me(client, master):
    headers, _ = master
    r = client.patch(f"{M}/me", json={"bio": "Yangi bio", "district": "Yunusobod"}, headers=headers)
    assert r.status_code == 200
    assert r.json()["bio"] == "Yangi bio"
    assert r.json()["district"] == "Yunusobod"
    assert r.json()["city"] == "Toshkent"
    assert client.patch(f"{M}/me", json={"city": None}, headers=headers).status_code == 422
    assert client.patch(f"{M}/me", json={"city": " "}, headers=headers).status_code == 422


def test_patch_me_cannot_escalate(client, master):
    headers, _ = master
    r = client.patch(f"{M}/me", json={"is_approved": True, "rating_avg": 5}, headers=headers)
    assert r.status_code == 200
    assert r.json()["is_approved"] is False
    assert r.json()["rating_avg"] == 0


# ---------- xizmatlar ----------

def put_services(client, headers, items):
    return client.put(f"{M}/me/services", json=items, headers=headers)


def test_services_replace(client, master, make_category):
    headers, _ = master
    c1 = make_category("Santexnik", "santexnik")
    c2 = make_category("Elektrik", "elektrik")
    r = put_services(client, headers, [
        {"category_id": c1.id, "pricing_type": "fixed", "base_price": 150000},
        {"category_id": c2.id, "pricing_type": "quote", "base_price": 999},
    ])
    assert r.status_code == 200
    by_cat = {s["category_id"]: s for s in r.json()["services"]}
    assert by_cat[c1.id]["base_price"] == 150000
    assert by_cat[c2.id]["pricing_type"] == "quote"
    assert by_cat[c2.id]["base_price"] is None  # quote narxi tozalanadi

    # Almashtirish: faqat bittasi qoladi
    r = put_services(client, headers, [{"category_id": c1.id, "pricing_type": "quote"}])
    assert [s["category_id"] for s in r.json()["services"]] == [c1.id]
    assert r.json()["services"][0]["base_price"] is None
    # Bo'sh ro'yxat hammasini o'chiradi
    assert put_services(client, headers, []).json()["services"] == []


def test_services_fixed_requires_price(client, master, make_category):
    headers, _ = master
    c = make_category()
    for price in (None, 0, -5):
        item = {"category_id": c.id, "pricing_type": "fixed"}
        if price is not None:
            item["base_price"] = price
        assert put_services(client, headers, [item]).status_code == 422
    # Float va satr narx rad etiladi (pul butun son)
    for bad in (100.5, "100"):
        assert put_services(client, headers, [
            {"category_id": c.id, "pricing_type": "fixed", "base_price": bad}
        ]).status_code == 422


def test_services_bad_pricing_type(client, master, make_category):
    headers, _ = master
    c = make_category()
    assert put_services(client, headers, [{"category_id": c.id, "pricing_type": "free"}]).status_code == 422


def test_services_duplicate_category(client, master, make_category):
    headers, _ = master
    c = make_category()
    item = {"category_id": c.id, "pricing_type": "quote"}
    assert put_services(client, headers, [item, item]).status_code == 422


def test_services_inactive_or_missing_category(client, master, make_category):
    headers, _ = master
    inactive = make_category("Eski", "eski", is_active=False)
    assert put_services(client, headers, [{"category_id": inactive.id, "pricing_type": "quote"}]).status_code == 422
    assert put_services(client, headers, [{"category_id": 9999, "pricing_type": "quote"}]).status_code == 422


def test_failed_put_keeps_old_services(client, master, make_category):
    headers, _ = master
    c = make_category()
    put_services(client, headers, [{"category_id": c.id, "pricing_type": "quote"}])
    put_services(client, headers, [{"category_id": 9999, "pricing_type": "quote"}])
    assert len(client.get(f"{M}/me", headers=headers).json()["services"]) == 1


# ---------- bandlik va tasdiqlash ----------

def test_availability_toggle_hides_from_list(client, master, admin_headers):
    headers, pid = master
    approve(client, admin_headers, pid)
    assert len(listing(client)) == 1

    r = client.patch(f"{M}/me/availability", json={"is_available": False}, headers=headers)
    assert r.status_code == 200 and r.json()["is_available"] is False
    assert listing(client) == []
    # Tasdiqlangan band usta alohida sahifada ko'rinadi
    assert client.get(f"{M}/{pid}").status_code == 200

    client.patch(f"{M}/me/availability", json={"is_available": True}, headers=headers)
    assert len(listing(client)) == 1


def test_availability_requires_bool(client, master):
    headers, _ = master
    assert client.patch(f"{M}/me/availability", json={"is_available": "yes"}, headers=headers).status_code == 422
    assert client.patch(f"{M}/me/availability", json={}, headers=headers).status_code == 422


def test_admin_approval_makes_visible_and_revoke(client, master, admin_headers):
    _, pid = master
    assert listing(client) == []
    approve(client, admin_headers, pid, True)
    assert [m["id"] for m in listing(client)] == [pid]
    approve(client, admin_headers, pid, False)
    assert listing(client) == []


def test_approval_permissions(client, master, signup, admin_headers):
    headers, pid = master
    url = f"/api/v1/admin/masters/{pid}/approval"
    assert client.patch(url, json={"is_approved": True}).status_code == 401
    assert client.patch(url, json={"is_approved": True}, headers=headers).status_code == 403
    assert client.patch("/api/v1/admin/masters/9999/approval", json={"is_approved": True}, headers=admin_headers).status_code == 404


# ---------- ommaviy ro'yxat ----------

def make_approved_master(client, signup, admin_headers, make_category, phone, name, city, district, cat_ids):
    headers, _ = signup("master", phone, name)
    pid = create_profile(client, headers, city=city, district=district).json()["id"]
    put_services(client, headers, [
        {"category_id": c, "pricing_type": "fixed", "base_price": 100000} for c in cat_ids
    ])
    approve(client, admin_headers, pid)
    return pid


def test_filters(client, signup, admin_headers, make_category):
    plumb = make_category("Santexnik", "santexnik")
    elec = make_category("Elektrik", "elektrik")
    a = make_approved_master(client, signup, admin_headers, make_category,
                             "+998902222221", "Aziz", "Toshkent", "Chilonzor", [plumb.id])
    b = make_approved_master(client, signup, admin_headers, make_category,
                             "+998902222222", "Jasur", "Toshkent", "Yunusobod", [elec.id])
    c = make_approved_master(client, signup, admin_headers, make_category,
                             "+998902222223", "Bobur", "Samarqand", "Registon", [plumb.id, elec.id])

    ids = lambda **p: sorted(m["id"] for m in listing(client, **p))
    assert ids() == sorted([a, b, c])
    assert ids(category_id=plumb.id) == sorted([a, c])
    assert ids(category_id=elec.id) == sorted([b, c])
    assert ids(city="toshkent") == sorted([a, b])  # katta-kichik harf farqsiz
    assert ids(city="TOSHKENT", district="chilonzor") == [a]
    assert ids(district="REGISTON") == [c]
    assert ids(category_id=plumb.id, city="Toshkent") == [a]
    assert ids(city="Buxoro") == []
    assert ids(category_id=9999) == []


def test_blocked_master_hidden(client, db, master, admin_headers):
    from app import models
    _, pid = master
    approve(client, admin_headers, pid)
    profile = db.get(models.MasterProfile, pid)
    user = db.get(models.User, profile.user_id)
    user.is_active = False
    db.commit()
    assert listing(client) == []
    assert client.get(f"{M}/{pid}").status_code == 404


def test_ordering(client, db, signup, admin_headers, make_category):
    from app import models
    cat = make_category()
    ids = [
        make_approved_master(client, signup, admin_headers, make_category,
                             f"+99890222222{i}", f"Usta{i}", "Toshkent", "Chilonzor", [cat.id])
        for i in range(1, 5)
    ]
    ratings = {ids[0]: (4.0, 10), ids[1]: (5.0, 2), ids[2]: (5.0, 7), ids[3]: (0.0, 0)}
    for pid, (avg, cnt) in ratings.items():
        p = db.get(models.MasterProfile, pid)
        p.rating_avg, p.rating_count = avg, cnt
    db.commit()
    assert [m["id"] for m in listing(client)] == [ids[2], ids[1], ids[0], ids[3]]


def test_get_master_unapproved_404(client, master):
    _, pid = master
    r = client.get(f"{M}/{pid}")
    assert r.status_code == 404
    assert client.get(f"{M}/9999").status_code == 404


def test_get_master_ok_and_no_secrets(client, signup, admin_headers, make_category):
    cat = make_category()
    pid = make_approved_master(client, signup, admin_headers, make_category,
                               "+998902222221", "Aziz Karimov", "Toshkent", "Chilonzor", [cat.id])
    r = client.get(f"{M}/{pid}")
    assert r.status_code == 200
    body = r.json()
    assert body["full_name"] == "Aziz Karimov"
    assert body["services"][0]["category_name"] == "Santexnik"
    assert body["services"][0]["base_price"] == 100000
    assert_no_secrets(r.text)
    assert_no_secrets(client.get(M).text)
