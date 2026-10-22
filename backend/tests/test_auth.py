from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import Depends

from app import models
from app.api.deps import require_role
from app.api.v1.auth import _failed_attempts
from app.core.config import settings
from app.core.security import create_access_token, decode_access_token
from app.main import app
from app.models.enums import Role
from app.schemas.auth import normalize_phone

REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"
ME = "/api/v1/auth/me"
CHANGE_PASSWORD = "/api/v1/auth/change-password"

CUSTOMER = {
    "phone": "+998901234567",
    "password": "secret123",
    "full_name": "Ali Valiyev",
    "role": "customer",
}


@pytest.fixture(autouse=True)
def clean_failed_attempts():
    _failed_attempts.clear()
    yield
    _failed_attempts.clear()


def register(client, **overrides):
    return client.post(REGISTER, json={**CUSTOMER, **overrides})


# ---------- register ----------

def test_register_customer(client):
    r = register(client)
    assert r.status_code == 201
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["user"]["role"] == "customer"
    assert body["user"]["phone"] == "+998901234567"
    assert "password_hash" not in body["user"]
    assert "password" not in body["user"]


def test_register_master(client):
    r = register(client, phone="+998907654321", role="master")
    assert r.status_code == 201
    assert r.json()["user"]["role"] == "master"


def test_register_admin_role_rejected(client):
    assert register(client, role="admin").status_code == 422


def test_register_extra_fields_cannot_escalate(client, db):
    r = register(client, is_active=False, is_approved=True, is_admin=True)
    assert r.status_code == 201
    assert r.json()["user"]["is_active"] is True
    assert r.json()["user"]["role"] == "customer"
    user = db.query(models.User).one()
    assert user.is_active is True
    assert user.role == Role.CUSTOMER
    # Usta profili ham yaratilmaydi / tasdiqlanmaydi
    assert db.query(models.MasterProfile).count() == 0


def test_register_duplicate_phone(client):
    assert register(client).status_code == 201
    r = register(client)
    assert r.status_code == 409
    assert r.json()["detail"] == "Bu telefon raqami allaqachon ro'yxatdan o'tgan"


def test_register_phone_normalization(client):
    assert register(client, phone="90 123-45-67").status_code == 201
    r = register(client, phone="998901234567")
    assert r.status_code == 409


@pytest.mark.parametrize(
    "raw",
    ["90 123-45-67", "998901234567", "+998901234567", " +998 (90) 123-45-67 "],
)
def test_normalize_phone_ok(raw):
    assert normalize_phone(raw) == "+998901234567"


@pytest.mark.parametrize("raw", ["", "123", "+99890123456", "abc", "+7901234567890"])
def test_normalize_phone_bad(raw):
    with pytest.raises(ValueError):
        normalize_phone(raw)


@pytest.mark.parametrize(
    "overrides",
    [
        {"phone": "12345"},
        {"phone": "salom"},
        {"password": "short"},
        {"password": "x" * 73},
        {"password": "onlyletters"},
        {"password": "12345678"},
        {"full_name": "A"},
        {"full_name": "x" * 121},
        {"role": "superuser"},
        {"role": ""},
    ],
)
def test_register_validation_errors(client, overrides):
    assert register(client, **overrides).status_code == 422


def test_register_missing_fields(client):
    assert client.post(REGISTER, json={}).status_code == 422


# ---------- login ----------

def test_login_ok(client):
    register(client)
    r = client.post(LOGIN, json={"phone": "90 123-45-67", "password": "secret123"})
    assert r.status_code == 200
    assert r.json()["user"]["phone"] == "+998901234567"
    assert r.json()["access_token"]


def test_login_wrong_password_and_unknown_phone_identical(client):
    register(client)
    wrong = client.post(LOGIN, json={"phone": CUSTOMER["phone"], "password": "wrongpass1"})
    unknown = client.post(LOGIN, json={"phone": "+998909999999", "password": "secret123"})
    assert wrong.status_code == 401
    assert unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert wrong.json()["detail"] == "Telefon yoki parol noto'g'ri"


def test_blocked_user(client, db, auth_header):
    token = register(client).json()["access_token"]
    assert client.get(ME, headers=auth_header(token)).status_code == 200

    user = db.query(models.User).one()
    user.is_active = False
    db.commit()

    r = client.post(LOGIN, json={"phone": CUSTOMER["phone"], "password": "secret123"})
    assert r.status_code == 403
    assert r.json()["detail"] == "Akkaunt bloklangan"
    # Eski token ham ishlamaydi
    assert client.get(ME, headers=auth_header(token)).status_code == 401


def test_admin_can_login(client, make_admin):
    make_admin()
    r = client.post(LOGIN, json={"phone": "+998900000000", "password": "admin12345"})
    assert r.status_code == 200
    assert r.json()["user"]["role"] == "admin"


def test_login_rate_limiting_blocks_after_five_failed_attempts(client):
    register(client)
    # Dastlabki 5 ta xato urinish -> 401
    for _ in range(5):
        r = client.post(LOGIN, json={"phone": CUSTOMER["phone"], "password": "wrongpass1"})
        assert r.status_code == 401

    # 6-urinish -> 429 Too Many Requests
    r = client.post(LOGIN, json={"phone": CUSTOMER["phone"], "password": "wrongpass1"})
    assert r.status_code == 429
    assert "Juda ko'p" in r.json()["detail"]

    # Hatto to'g'ri parol kiritilsa ham vaqtinchalik bloklanadi
    r = client.post(LOGIN, json={"phone": CUSTOMER["phone"], "password": CUSTOMER["password"]})
    assert r.status_code == 429


# ---------- /me ----------

def test_me_without_token(client):
    r = client.get(ME)
    assert r.status_code == 401
    assert r.json()["detail"] == "Avtorizatsiya talab qilinadi"


def test_me_garbage_token(client, auth_header):
    assert client.get(ME, headers=auth_header("garbage.token.here")).status_code == 401


def test_me_token_other_key(client, db, auth_header):
    register(client)
    user = db.query(models.User).one()
    exp = datetime.now(timezone.utc) + timedelta(minutes=5)
    bad = jwt.encode(
        {"sub": str(user.id), "exp": exp}, "boshqa-kalit-" * 4, algorithm=settings.ALGORITHM
    )
    assert client.get(ME, headers=auth_header(bad)).status_code == 401


def test_me_expired_token(client, db, auth_header):
    register(client)
    user = db.query(models.User).one()
    exp = datetime.now(timezone.utc) - timedelta(minutes=1)
    old = jwt.encode(
        {"sub": str(user.id), "exp": exp}, settings.SECRET_KEY, algorithm=settings.ALGORITHM
    )
    assert client.get(ME, headers=auth_header(old)).status_code == 401


def test_me_token_for_missing_user(client, auth_header):
    assert client.get(ME, headers=auth_header(create_access_token(9999))).status_code == 401


def test_me_valid_token(client, auth_header):
    token = register(client).json()["access_token"]
    r = client.get(ME, headers=auth_header(token))
    assert r.status_code == 200
    assert r.json()["phone"] == CUSTOMER["phone"]
    assert "password_hash" not in r.json()


def test_decode_access_token():
    assert decode_access_token(create_access_token(5)) == 5
    assert decode_access_token("x") is None
    # alg=none hujumi
    none_tok = jwt.encode({"sub": "5"}, None, algorithm="none")
    assert decode_access_token(none_tok) is None


def test_token_contains_only_sub_and_exp():
    payload = jwt.decode(
        create_access_token(7), settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
    )
    assert set(payload) == {"sub", "exp"}


# ---------- change-password ----------

def test_change_password_unauthorized(client):
    r = client.post(
        CHANGE_PASSWORD,
        json={"current_password": "oldPassword1", "new_password": "newPassword2"},
    )
    assert r.status_code == 401


def test_change_password_success(client, auth_header):
    token = register(client).json()["access_token"]
    r = client.post(
        CHANGE_PASSWORD,
        headers=auth_header(token),
        json={"current_password": "secret123", "new_password": "newSecret456"},
    )
    assert r.status_code == 200
    assert r.json()["detail"] == "Parol muvaffaqiyatli o'zgartirildi"

    # Eski parol bilan login qilib bo'lmaydi
    old_login = client.post(
        LOGIN, json={"phone": CUSTOMER["phone"], "password": "secret123"}
    )
    assert old_login.status_code == 401

    # Yangi parol bilan login ishlaydi
    new_login = client.post(
        LOGIN, json={"phone": CUSTOMER["phone"], "password": "newSecret456"}
    )
    assert new_login.status_code == 200
    assert new_login.json()["access_token"]


def test_change_password_wrong_current(client, auth_header):
    token = register(client).json()["access_token"]
    r = client.post(
        CHANGE_PASSWORD,
        headers=auth_header(token),
        json={"current_password": "wrongPassword9", "new_password": "newSecret456"},
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "Joriy parol noto'g'ri"


def test_change_password_same_as_current(client, auth_header):
    token = register(client).json()["access_token"]
    r = client.post(
        CHANGE_PASSWORD,
        headers=auth_header(token),
        json={"current_password": "secret123", "new_password": "secret123"},
    )
    assert r.status_code == 400
    assert "bir xil" in r.json()["detail"]


@pytest.mark.parametrize(
    "bad_new_password",
    [
        "short",             # < 8
        "onlylettershere",   # raqam yo'q
        "1234567890",        # harf yo'q
        "x" * 73,            # > 72
    ],
)
def test_change_password_complexity_rejected(client, auth_header, bad_new_password):
    token = register(client).json()["access_token"]
    r = client.post(
        CHANGE_PASSWORD,
        headers=auth_header(token),
        json={"current_password": "secret123", "new_password": bad_new_password},
    )
    assert r.status_code == 422


# ---------- require_role ----------

@pytest.fixture
def role_routes():
    @app.get("/__test/admin-only")
    def admin_only(user=Depends(require_role(Role.ADMIN))):
        return {"id": user.id}

    @app.get("/__test/master-or-customer")
    def multi(user=Depends(require_role("master", "customer"))):
        return {"id": user.id}

    added = app.router.routes[-2:]
    yield
    for route in added:
        app.router.routes.remove(route)


def test_require_role(client, make_admin, auth_header, role_routes):
    customer_token = register(client).json()["access_token"]
    master_token = register(client, phone="+998907654321", role="master").json()[
        "access_token"
    ]
    make_admin()
    admin_token = client.post(
        LOGIN, json={"phone": "+998900000000", "password": "admin12345"}
    ).json()["access_token"]

    # token yo'q -> 401
    assert client.get("/__test/admin-only").status_code == 401
    # noto'g'ri rol -> 403
    for tok in (customer_token, master_token):
        r = client.get("/__test/admin-only", headers=auth_header(tok))
        assert r.status_code == 403
        assert r.json()["detail"] == "Bu amal uchun ruxsat yo'q"
    # to'g'ri rol -> 200
    assert client.get("/__test/admin-only", headers=auth_header(admin_token)).status_code == 200
    # bir nechta rol
    assert client.get("/__test/master-or-customer", headers=auth_header(master_token)).status_code == 200
    assert client.get("/__test/master-or-customer", headers=auth_header(customer_token)).status_code == 200
    assert client.get("/__test/master-or-customer", headers=auth_header(admin_token)).status_code == 403
