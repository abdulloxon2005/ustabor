CATS = "/api/v1/categories"
ADMIN_CATS = "/api/v1/admin/categories"


def test_public_list_only_active_ordered_by_name(client, make_category):
    make_category("Zargar", "zargar")
    make_category("Elektrik", "elektrik")
    make_category("Yashirin", "yashirin", is_active=False)
    r = client.get(CATS)  # tokensiz
    assert r.status_code == 200
    assert [c["name"] for c in r.json()] == ["Elektrik", "Zargar"]


def test_anonymous_cannot_create(client):
    assert client.post(ADMIN_CATS, json={"name": "Yangi"}).status_code == 401


def test_non_admin_cannot_create(client, signup):
    for role, phone in (("customer", "+998901111111"), ("master", "+998902222222")):
        headers, _ = signup(role, phone)
        r = client.post(ADMIN_CATS, json={"name": "Yangi"}, headers=headers)
        assert r.status_code == 403


def test_admin_creates_with_auto_slug(client, admin_headers):
    r = client.post(ADMIN_CATS, json={"name": "Ta'mirlash va qurilish"}, headers=admin_headers)
    assert r.status_code == 201
    assert r.json()["slug"] == "tamirlash-va-qurilish"
    assert r.json()["is_active"] is True
    assert len(client.get(CATS).json()) == 1


def test_admin_creates_with_given_slug(client, admin_headers):
    r = client.post(ADMIN_CATS, json={"name": "Bog'bon", "slug": "bogbon"}, headers=admin_headers)
    assert r.status_code == 201
    assert r.json()["slug"] == "bogbon"


def test_bad_slug_422(client, admin_headers):
    r = client.post(ADMIN_CATS, json={"name": "Yangi", "slug": "Bad Slug!"}, headers=admin_headers)
    assert r.status_code == 422


def test_duplicate_slug_409(client, admin_headers, make_category):
    make_category("Santexnik", "santexnik")
    r = client.post(
        ADMIN_CATS, json={"name": "Boshqa", "slug": "santexnik"}, headers=admin_headers
    )
    assert r.status_code == 409
    # avto-slug to'qnashuvi ham 409
    r = client.post(ADMIN_CATS, json={"name": "Santexnik"}, headers=admin_headers)
    assert r.status_code == 409


def test_admin_patch(client, admin_headers, make_category):
    c = make_category("Elektrik", "elektrik")
    r = client.patch(
        f"{ADMIN_CATS}/{c.id}", json={"name": "Elektrik usta", "is_active": False},
        headers=admin_headers,
    )
    assert r.status_code == 200
    assert r.json()["name"] == "Elektrik usta"
    assert r.json()["slug"] == "elektrik"  # slug o'zgarmaydi
    assert client.get(CATS).json() == []


def test_patch_forbidden_and_missing(client, admin_headers, signup, make_category):
    c = make_category()
    headers, _ = signup("customer")
    assert client.patch(f"{ADMIN_CATS}/{c.id}", json={"is_active": False}, headers=headers).status_code == 403
    assert client.patch(f"{ADMIN_CATS}/{c.id}", json={"is_active": False}).status_code == 401
    assert client.patch(f"{ADMIN_CATS}/9999", json={"is_active": False}, headers=admin_headers).status_code == 404
