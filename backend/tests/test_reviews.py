"""Unit testlar: reviews xizmati va reytingni qayta hisoblash (HTTP yo'q)."""

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app import models
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.enums import OrderStatus, Role, SelectionMode
from app.services.reviews import create_review, recompute_master_rating


def _user(db, phone: str, role: Role = Role.CUSTOMER, full_name: str = "Test Foydalanuvchi") -> models.User:
    u = models.User(
        phone=phone,
        password_hash=hash_password("secret123"),
        full_name=full_name,
        role=role,
        is_active=True,
    )
    db.add(u)
    db.flush()
    return u


def _master(db, user: models.User, city: str = "Toshkent", district: str = "Chilonzor") -> models.MasterProfile:
    mp = models.MasterProfile(
        user_id=user.id,
        city=city,
        district=district,
        is_approved=True,
    )
    db.add(mp)
    db.flush()
    return mp


def _category(db, name: str = "Santexnik", slug: str = "santexnik") -> models.Category:
    c = models.Category(name=name, slug=slug, is_active=True)
    db.add(c)
    db.flush()
    return c


def _order(
    db,
    customer: models.User,
    category: models.Category,
    master: models.MasterProfile | None = None,
    status: OrderStatus = OrderStatus.COMPLETED,
    agreed_price: int = 100_000,
) -> models.Order:
    o = models.Order(
        customer_id=customer.id,
        category_id=category.id,
        master_id=master.id if master else None,
        description="Test buyurtma tavsifi",
        city="Toshkent",
        district="Chilonzor",
        address="Test ko'chasi 1-uy",
        status=status,
        selection_mode=SelectionMode.AUTOMATIC,
        agreed_price=agreed_price,
    )
    db.add(o)
    db.flush()
    return o


def test_happy_path_rating_count_and_avg(db):
    """Happy path: 5 keyin 4 baholari -> count 2, avg 4.5."""
    c = _category(db)
    cust = _user(db, "+998901111111", Role.CUSTOMER)
    m_user = _user(db, "+998902222222", Role.MASTER)
    mp = _master(db, m_user)

    order1 = _order(db, cust, c, mp, status=OrderStatus.COMPLETED)
    rev1 = create_review(db, order1, cust, rating=5, comment="  Juda a'lo darajada!  ")
    db.flush()

    assert rev1.rating == 5
    assert rev1.comment == "Juda a'lo darajada!"
    assert mp.rating_count == 1
    assert mp.rating_avg == 5.0

    order2 = _order(db, cust, c, mp, status=OrderStatus.COMPLETED)
    rev2 = create_review(db, order2, cust, rating=4, comment=None)
    db.flush()

    assert rev2.rating == 4
    assert rev2.comment is None
    assert mp.rating_count == 2
    assert mp.rating_avg == 4.5


def test_order_not_completed_409(db):
    """Yakunlanmagan buyurtmaga sharh qoldirish 409 beradi."""
    c = _category(db)
    cust = _user(db, "+998901111112", Role.CUSTOMER)
    m_user = _user(db, "+998902222223", Role.MASTER)
    mp = _master(db, m_user)

    for st in [OrderStatus.SEARCHING, OrderStatus.ASSIGNED, OrderStatus.IN_PROGRESS, OrderStatus.CANCELLED]:
        order = _order(db, cust, c, mp, status=st)
        with pytest.raises(HTTPException) as exc_info:
            create_review(db, order, cust, rating=5)
        assert exc_info.value.status_code == 409
        assert "yakunlangan buyurtmaga" in exc_info.value.detail


def test_second_review_409_and_stats_unchanged(db):
    """Bir buyurtmaga ikkinchi sharh 409 qaytaradi va usta statistikasi o'zgarmaydi."""
    c = _category(db)
    cust = _user(db, "+998901111113", Role.CUSTOMER)
    m_user = _user(db, "+998902222224", Role.MASTER)
    mp = _master(db, m_user)

    order = _order(db, cust, c, mp, status=OrderStatus.COMPLETED)
    create_review(db, order, cust, rating=5)
    db.flush()

    assert mp.rating_count == 1
    assert mp.rating_avg == 5.0

    with pytest.raises(HTTPException) as exc_info:
        create_review(db, order, cust, rating=3)
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Bu buyurtmaga sharh allaqachon qoldirilgan"

    # Statistika o'zgarmasligi shart
    assert mp.rating_count == 1
    assert mp.rating_avg == 5.0


@pytest.mark.parametrize("invalid_rating", [0, 6, -1, 10, 3.5, True, False, "5", None])
def test_invalid_ratings_rejected(db, invalid_rating):
    """0, 6, manfiy, float, boolean yoki matnli baholar rad etiladi (422)."""
    c = _category(db)
    cust = _user(db, "+998901111114", Role.CUSTOMER)
    m_user = _user(db, "+998902222225", Role.MASTER)
    mp = _master(db, m_user)
    order = _order(db, cust, c, mp, status=OrderStatus.COMPLETED)

    with pytest.raises(HTTPException) as exc_info:
        create_review(db, order, cust, rating=invalid_rating)
    assert exc_info.value.status_code == 422


def test_comment_validation(db):
    """Sharh 1000 belgidan oshsa 422 beradi, bo'sh joylar strip qilinadi."""
    c = _category(db)
    cust = _user(db, "+998901111115", Role.CUSTOMER)
    m_user = _user(db, "+998902222226", Role.MASTER)
    mp = _master(db, m_user)
    order = _order(db, cust, c, mp, status=OrderStatus.COMPLETED)

    too_long = "a" * 1001
    with pytest.raises(HTTPException) as exc_info:
        create_review(db, order, cust, rating=5, comment=too_long)
    assert exc_info.value.status_code == 422

    # Bo'sh sharh None ga aylanadi
    rev = create_review(db, order, cust, rating=5, comment="   ")
    assert rev.comment is None


def test_other_customer_order_rejected(db):
    """Boshqa mijozning buyurtmasiga sharh qoldirib bo'lmaydi."""
    c = _category(db)
    cust1 = _user(db, "+998901111116", Role.CUSTOMER)
    cust2 = _user(db, "+998901111117", Role.CUSTOMER)
    m_user = _user(db, "+998902222227", Role.MASTER)
    mp = _master(db, m_user)

    order = _order(db, cust1, c, mp, status=OrderStatus.COMPLETED)

    with pytest.raises(HTTPException) as exc_info:
        create_review(db, order, cust2, rating=5)
    assert exc_info.value.status_code in (403, 404)


def test_recompute_after_deleting_review_corrects_numbers(db):
    """Sharh o'chirilgach recompute chaqirilsa reyting to'g'irlanadi."""
    c = _category(db)
    cust = _user(db, "+998901111118", Role.CUSTOMER)
    m_user = _user(db, "+998902222228", Role.MASTER)
    mp = _master(db, m_user)

    order1 = _order(db, cust, c, mp, status=OrderStatus.COMPLETED)
    order2 = _order(db, cust, c, mp, status=OrderStatus.COMPLETED)

    rev1 = create_review(db, order1, cust, rating=5)
    rev2 = create_review(db, order2, cust, rating=4)
    db.flush()

    assert mp.rating_count == 2
    assert mp.rating_avg == 4.5

    # 1-sharhni o'chiramiz
    db.delete(rev1)
    db.flush()

    recompute_master_rating(db, mp.id)
    assert mp.rating_count == 1
    assert mp.rating_avg == 4.0

    # 2-sharhni ham o'chiramiz
    db.delete(rev2)
    db.flush()

    recompute_master_rating(db, mp.id)
    assert mp.rating_count == 0
    assert mp.rating_avg == 0.0


def test_unique_constraint_race_two_sessions(db):
    """Ikki sessiyada bir vaqtda sharh qoldirilganda bittasi o'tadi, ikkinchisi 409 oladi."""
    c = _category(db)
    cust = _user(db, "+998901111119", Role.CUSTOMER)
    m_user = _user(db, "+998902222229", Role.MASTER)
    mp = _master(db, m_user)
    order = _order(db, cust, c, mp, status=OrderStatus.COMPLETED)
    db.commit()

    order_id = order.id
    cust_id = cust.id

    session_b = SessionLocal()
    try:
        order_b = session_b.get(models.Order, order_id)
        cust_b = session_b.get(models.User, cust_id)

        # Sessiya A birinchi sharh qoldiradi va commit qiladi
        create_review(db, order, cust, rating=5, comment="A sessiyasi")
        db.commit()

        # Sessiya B ham sharh qoldirishga urinadi
        with pytest.raises(HTTPException) as exc_info:
            create_review(session_b, order_b, cust_b, rating=4, comment="B sessiyasi")
        assert exc_info.value.status_code == 409

        # Bazada aynan 1 ta sharh bor
        reviews = db.scalars(select(models.Review).where(models.Review.order_id == order_id)).all()
        assert len(reviews) == 1
        assert reviews[0].rating == 5
    finally:
        session_b.close()
