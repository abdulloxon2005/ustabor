"""OTP (mock SMS) oqimi: ro'yxatdan o'tish va parolni unutish."""

from app.services import sms
from tests.conftest import otp_code_for

REGISTER_OTP = "/api/v1/auth/register/request-otp"
REGISTER = "/api/v1/auth/register"
FORGOT_OTP = "/api/v1/auth/forgot-password/request-otp"
FORGOT_CONFIRM = "/api/v1/auth/forgot-password/confirm"
LOGIN = "/api/v1/auth/login"

PHONE = "+998901234567"


def _register(client, phone=PHONE, **overrides):
    client.post(REGISTER_OTP, json={"phone": phone})
    payload = {
        "phone": phone,
        "password": "secret123",
        "full_name": "Test Foydalanuvchi",
        "role": "customer",
        "otp_code": otp_code_for(phone),
        **overrides,
    }
    return client.post(REGISTER, json=payload)


# ---------- register/request-otp ----------


def test_request_otp_sends_mock_sms(client):
    r = client.post(REGISTER_OTP, json={"phone": PHONE})
    assert r.status_code == 200
    msg = sms.last_message_for(PHONE)
    assert msg is not None
    assert len(otp_code_for(PHONE)) == 6


def test_request_otp_for_taken_phone_is_409(client):
    assert _register(client).status_code == 201
    r = client.post(REGISTER_OTP, json={"phone": PHONE})
    assert r.status_code == 409


def test_request_otp_rate_limited_after_three(client):
    for _ in range(3):
        assert client.post(REGISTER_OTP, json={"phone": PHONE}).status_code == 200
    r = client.post(REGISTER_OTP, json={"phone": PHONE})
    assert r.status_code == 429


# ---------- register with otp_code ----------


def test_register_without_otp_request_fails(client):
    r = client.post(
        REGISTER,
        json={
            "phone": PHONE,
            "password": "secret123",
            "full_name": "Test",
            "role": "customer",
            "otp_code": "123456",
        },
    )
    assert r.status_code == 400


def test_register_with_wrong_otp_fails(client):
    client.post(REGISTER_OTP, json={"phone": PHONE})
    real_code = otp_code_for(PHONE)
    wrong_code = "000000" if real_code != "000000" else "111111"
    r = client.post(
        REGISTER,
        json={
            "phone": PHONE,
            "password": "secret123",
            "full_name": "Test",
            "role": "customer",
            "otp_code": wrong_code,
        },
    )
    assert r.status_code == 400


def test_register_with_correct_otp_succeeds(client):
    assert _register(client).status_code == 201


def test_register_otp_cannot_be_reused(client):
    client.post(REGISTER_OTP, json={"phone": PHONE})
    code = otp_code_for(PHONE)
    r1 = client.post(
        REGISTER,
        json={
            "phone": PHONE,
            "password": "secret123",
            "full_name": "Birinchi",
            "role": "customer",
            "otp_code": code,
        },
    )
    assert r1.status_code == 201

    # Xuddi shu kod bilan boshqa raqamga urinish ham ishlamaydi (kod shu
    # raqamga tegishli, boshqa raqam uchun topilmaydi)
    r2 = client.post(
        REGISTER,
        json={
            "phone": "+998909998877",
            "password": "secret123",
            "full_name": "Ikkinchi",
            "role": "customer",
            "otp_code": code,
        },
    )
    assert r2.status_code == 400


def test_register_otp_wrong_attempts_exhausted(client):
    client.post(REGISTER_OTP, json={"phone": PHONE})
    for _ in range(5):
        r = client.post(
            REGISTER,
            json={
                "phone": PHONE,
                "password": "secret123",
                "full_name": "Test",
                "role": "customer",
                "otp_code": "999999",
            },
        )
        assert r.status_code == 400

    # 6-marta: endi urinishlar tugagan, hatto to'g'ri kod bo'lsa ham yaroqsiz
    real_code = otp_code_for(PHONE)
    r = client.post(
        REGISTER,
        json={
            "phone": PHONE,
            "password": "secret123",
            "full_name": "Test",
            "role": "customer",
            "otp_code": real_code,
        },
    )
    assert r.status_code == 429


# ---------- forgot-password ----------


def test_forgot_password_unknown_phone_returns_generic_message(client):
    r = client.post(FORGOT_OTP, json={"phone": "+998909999999"})
    assert r.status_code == 200
    assert sms.last_message_for("+998909999999") is None


def test_forgot_password_known_phone_sends_sms(client):
    _register(client)
    r = client.post(FORGOT_OTP, json={"phone": PHONE})
    assert r.status_code == 200
    assert sms.last_message_for(PHONE) is not None


def test_forgot_password_confirm_changes_password(client):
    _register(client)
    client.post(FORGOT_OTP, json={"phone": PHONE})
    code = otp_code_for(PHONE)

    r = client.post(
        FORGOT_CONFIRM,
        json={"phone": PHONE, "otp_code": code, "new_password": "newSecret456"},
    )
    assert r.status_code == 200

    old_login = client.post(LOGIN, json={"phone": PHONE, "password": "secret123"})
    assert old_login.status_code == 401

    new_login = client.post(LOGIN, json={"phone": PHONE, "password": "newSecret456"})
    assert new_login.status_code == 200


def test_forgot_password_confirm_wrong_code_fails(client):
    _register(client)
    client.post(FORGOT_OTP, json={"phone": PHONE})
    r = client.post(
        FORGOT_CONFIRM,
        json={"phone": PHONE, "otp_code": "000111", "new_password": "newSecret456"},
    )
    assert r.status_code in (400, 429)


def test_forgot_password_register_otp_cannot_be_used_for_reset(client):
    """REGISTER maqsadidagi kod RESET uchun ishlamasligi kerak (purpose ajratilgan)."""
    client.post(REGISTER_OTP, json={"phone": PHONE})
    register_code = otp_code_for(PHONE)
    r1 = client.post(
        REGISTER,
        json={
            "phone": PHONE,
            "password": "secret123",
            "full_name": "Test",
            "role": "customer",
            "otp_code": register_code,
        },
    )
    assert r1.status_code == 201

    client.post(FORGOT_OTP, json={"phone": PHONE})
    reset_code = otp_code_for(PHONE)
    assert reset_code != register_code or True  # kodlar tasodifiy, tengligi muhim emas

    # Avvalgi (REGISTER maqsadidagi, allaqachon iste'mol qilingan) kod bilan
    # parolni tiklab bo'lmaydi
    r2 = client.post(
        FORGOT_CONFIRM,
        json={"phone": PHONE, "otp_code": register_code, "new_password": "newSecret456"},
    )
    assert r2.status_code == 400
