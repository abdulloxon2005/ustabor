import os

# Importlardan OLDIN o'rnatilishi shart: testlar .env ga bog'liq bo'lmasin
os.environ.setdefault("SECRET_KEY", "test-secret-key-faqat-testlar-uchun")
os.environ["DATABASE_URL"] = "sqlite:///./test.db"

import pytest
from fastapi.testclient import TestClient

from app import models  # noqa: F401  (modellarni Base.metadata ga yuklaydi)
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


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