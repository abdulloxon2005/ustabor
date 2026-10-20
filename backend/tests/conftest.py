import os

# Importlardan OLDIN o'rnatilishi shart: testlar .env ga bog'liq bo'lmasin
os.environ.setdefault("SECRET_KEY", "test-secret-key-faqat-testlar-uchun")
os.environ["DATABASE_URL"] = "sqlite:///./test.db"

import pytest
from fastapi.testclient import TestClient

from app import models  # noqa: F401  (modellarni Base.metadata ga yuklaydi)
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models.enums import Role


@pytest.fixture
def db():
    """Har test uchun toza jadvallar; test tugagach hammasi o'chiriladi."""
    Base.metadata.create_all(engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture
def client(db):
    # db ga bog'liq: jadvallar client ishlatilishidan oldin tayyor bo'ladi
    with TestClient(app) as c:
        yield c


@pytest.fixture
def make_admin(db):
    """Admin faqat bazaga to'g'ridan-to'g'ri qo'shiladi (API orqali emas)."""

    def _make(phone="+998900000000", password="admin12345", full_name="Admin"):
        user = models.User(
            phone=phone,
            password_hash=hash_password(password),
            full_name=full_name,
            role=Role.ADMIN,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    return _make


@pytest.fixture
def auth_header():
    def _header(token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    return _header


@pytest.fixture
def make_category(db):
    def _make(name="Santexnik", slug="santexnik", is_active=True):
        c = models.Category(name=name, slug=slug, is_active=is_active)
        db.add(c)
        db.commit()
        db.refresh(c)
        return c

    return _make


@pytest.fixture
def signup(client, auth_header):
    """API orqali ro'yxatdan o'tadi va (headers, user_dict) qaytaradi."""

    def _signup(role="customer", phone="+998901234567", full_name="Test Foydalanuvchi"):
        r = client.post(
            "/api/v1/auth/register",
            json={"phone": phone, "password": "secret123", "full_name": full_name, "role": role},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        return auth_header(body["access_token"]), body["user"]

    return _signup


@pytest.fixture
def admin_headers(client, make_admin, auth_header):
    make_admin()
    r = client.post(
        "/api/v1/auth/login", json={"phone": "+998900000000", "password": "admin12345"}
    )
    return auth_header(r.json()["access_token"])
