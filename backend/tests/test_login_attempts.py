"""Login urinishlarini DB (LoginAttempt) orqali cheklash.

test_auth.py da asosiy ssenariy (5 ta xato -> 429) bor; bu yerda DB-modelga
xos holatlar: muvaffaqiyatli login hisoblagichni tozalaydi, raqamlar bir-biriga
ta'sir qilmaydi, va hisoblagich app.models.LoginAttempt jadvalida saqlanadi.
"""

from app import models
from app.models.enums import Role
from app.core.security import hash_password

LOGIN = "/api/v1/auth/login"
REGISTER_OTP = "/api/v1/auth/register/request-otp"
REGISTER = "/api/v1/auth/register"

PHONE_A = "+998901111111"
PHONE_B = "+998902222222"


def _make_user(db, phone, password="secret123"):
    user = models.User(
        phone=phone,
        password_hash=hash_password(password),
        full_name="Test",
        role=Role.CUSTOMER,
    )
    db.add(user)
    db.commit()
    return user


def test_failed_attempts_recorded_in_db(client, db):
    _make_user(db, PHONE_A)
    for _ in range(3):
        client.post(LOGIN, json={"phone": PHONE_A, "password": "wrong"})

    count = db.query(models.LoginAttempt).filter_by(phone=PHONE_A).count()
    assert count == 3


def test_successful_login_clears_attempts(client, db):
    _make_user(db, PHONE_A)
    for _ in range(3):
        client.post(LOGIN, json={"phone": PHONE_A, "password": "wrong"})

    r = client.post(LOGIN, json={"phone": PHONE_A, "password": "secret123"})
    assert r.status_code == 200

    count = db.query(models.LoginAttempt).filter_by(phone=PHONE_A).count()
    assert count == 0

    # Hisoblagich tozalangani uchun yana xato urinishlar qila olish kerak
    for _ in range(4):
        r = client.post(LOGIN, json={"phone": PHONE_A, "password": "wrong"})
        assert r.status_code == 401


def test_attempts_are_scoped_per_phone(client, db):
    _make_user(db, PHONE_A)
    _make_user(db, PHONE_B)

    for _ in range(5):
        client.post(LOGIN, json={"phone": PHONE_A, "password": "wrong"})
    # A endi bloklangan
    assert client.post(LOGIN, json={"phone": PHONE_A, "password": "secret123"}).status_code == 429

    # B hali bloklanmagan
    r_b = client.post(LOGIN, json={"phone": PHONE_B, "password": "secret123"})
    assert r_b.status_code == 200
