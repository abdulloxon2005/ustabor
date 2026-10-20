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
