"""Usta haftalik ish jadvali (faqat ko'rsatish uchun)."""

SCHEDULE = "/api/v1/masters/me/schedule"


def _setup_master(client, signup):
    headers, _ = signup(role="master")
    r = client.post(
        "/api/v1/masters/profile",
        json={"bio": "Tajribali usta", "city": "Toshkent", "district": "Chilonzor"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return headers, r.json()["id"]


def test_default_schedule_is_full_week(client, db, signup):
    headers, _ = _setup_master(client, signup)
    r = client.get(SCHEDULE, headers=headers)
    assert r.status_code == 200
    days = r.json()
    assert len(days) == 7
    assert {d["weekday"] for d in days} == set(range(7))
    for d in days:
        assert d["is_working"] is True
        assert d["start_time"] == "09:00"
        assert d["end_time"] == "18:00"


def test_set_custom_schedule(client, db, signup):
    headers, master_id = _setup_master(client, signup)

    payload = [
        {"weekday": 0, "is_working": True, "start_time": "08:00", "end_time": "17:00"},
        {"weekday": 5, "is_working": False},
        {"weekday": 6, "is_working": False},
    ]
    r = client.put(SCHEDULE, json=payload, headers=headers)
    assert r.status_code == 200, r.text
    days = {d["weekday"]: d for d in r.json()}
    assert days[0]["start_time"] == "08:00"
    assert days[0]["end_time"] == "17:00"
    assert days[5]["is_working"] is False
    assert days[5]["start_time"] is None
    assert days[6]["is_working"] is False
    # Belgilanmagan kunlar standart holatda qoladi
    assert days[1]["is_working"] is True
    assert days[1]["start_time"] == "09:00"

    # Ommaviy profilda ham ko'rinadi
    r_pub = client.get(f"/api/v1/masters/{master_id}")
    # Hali tasdiqlanmagan -> 404, shuning uchun /me orqali tekshiramiz
    r_me = client.get("/api/v1/masters/me", headers=headers)
    assert r_me.status_code == 200
    me_days = {d["weekday"]: d for d in r_me.json()["schedule"]}
    assert me_days[0]["start_time"] == "08:00"
    assert me_days[5]["is_working"] is False


def test_set_schedule_replaces_previous(client, db, signup):
    headers, _ = _setup_master(client, signup)
    client.put(
        SCHEDULE,
        json=[{"weekday": 0, "is_working": False}],
        headers=headers,
    )
    r = client.get(SCHEDULE, headers=headers)
    days = {d["weekday"]: d for d in r.json()}
    assert days[0]["is_working"] is False

    # Qayta yuborilgan jadval eskisini to'liq almashtiradi
    r2 = client.put(
        SCHEDULE,
        json=[{"weekday": 0, "is_working": True, "start_time": "10:00", "end_time": "14:00"}],
        headers=headers,
    )
    days2 = {d["weekday"]: d for d in r2.json()}
    assert days2[0]["is_working"] is True
    assert days2[0]["start_time"] == "10:00"


def test_working_day_requires_times(client, db, signup):
    headers, _ = _setup_master(client, signup)
    r = client.put(
        SCHEDULE,
        json=[{"weekday": 0, "is_working": True}],
        headers=headers,
    )
    assert r.status_code == 422


def test_start_time_must_be_before_end_time(client, db, signup):
    headers, _ = _setup_master(client, signup)
    r = client.put(
        SCHEDULE,
        json=[{"weekday": 0, "is_working": True, "start_time": "18:00", "end_time": "09:00"}],
        headers=headers,
    )
    assert r.status_code == 422


def test_invalid_weekday_rejected(client, db, signup):
    headers, _ = _setup_master(client, signup)
    r = client.put(
        SCHEDULE,
        json=[{"weekday": 7, "is_working": False}],
        headers=headers,
    )
    assert r.status_code == 422


def test_duplicate_weekday_rejected(client, db, signup):
    headers, _ = _setup_master(client, signup)
    r = client.put(
        SCHEDULE,
        json=[
            {"weekday": 0, "is_working": False},
            {"weekday": 0, "is_working": True, "start_time": "09:00", "end_time": "18:00"},
        ],
        headers=headers,
    )
    assert r.status_code == 422


def test_invalid_time_format_rejected(client, db, signup):
    headers, _ = _setup_master(client, signup)
    r = client.put(
        SCHEDULE,
        json=[{"weekday": 0, "is_working": True, "start_time": "9:00", "end_time": "18:00"}],
        headers=headers,
    )
    assert r.status_code == 422


def test_customer_cannot_access_schedule(client, db, signup):
    cust_headers, _ = signup(role="customer")
    assert client.get(SCHEDULE, headers=cust_headers).status_code == 403
    assert client.put(SCHEDULE, json=[], headers=cust_headers).status_code == 403


def test_schedule_requires_auth(client):
    assert client.get(SCHEDULE).status_code == 401


def test_schedule_visible_in_masters_list(client, db, signup, make_admin, auth_header):
    headers, master_id = _setup_master(client, signup)
    client.put(
        SCHEDULE,
        json=[{"weekday": 2, "is_working": False}],
        headers=headers,
    )

    make_admin()
    r_admin = client.post(
        "/api/v1/auth/login", json={"phone": "+998900000000", "password": "admin12345"}
    )
    admin_headers = auth_header(r_admin.json()["access_token"])
    client.patch(
        f"/api/v1/admin/masters/{master_id}/approval",
        json={"is_approved": True},
        headers=admin_headers,
    )

    r_list = client.get("/api/v1/masters")
    assert r_list.status_code == 200
    found = next(m for m in r_list.json() if m["id"] == master_id)
    days = {d["weekday"]: d for d in found["schedule"]}
    assert days[2]["is_working"] is False
    assert days[0]["is_working"] is True
