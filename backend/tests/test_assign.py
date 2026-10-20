"""assign_master() atomik biriktirish testlari (HTTP yo'q, faqat db).

Testlar:
- Birinchi biriktirish muvaffaqiyatli
- Ikkinchi biriktirish (xuddi shu buyurtma) -> 409
- Stale session: ikki sessiyada bir vaqtda biriktirish
- Qidiruv bo'lmagan (cancelled) buyurtma -> 409
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app import models
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.enums import (
    OfferStatus,
    OrderStatus,
    PricingType,
    Role,
    SelectionMode,
)
from app.services.order_flow import assign_master


# ====== Yordamchi funksiyalar ======


def _user(db, phone, role=Role.MASTER, full_name="Test Usta", is_active=True):
    u = models.User(
        phone=phone,
        password_hash=hash_password("secret123"),
        full_name=full_name,
        role=role,
        is_active=is_active,
    )
    db.add(u)
    db.flush()
    return u


def _master(db, user, city="Toshkent", district="Yunusobod", is_approved=True):
    mp = models.MasterProfile(
        user_id=user.id,
        city=city,
        district=district,
        is_approved=is_approved,
    )
    db.add(mp)
    db.flush()
    return mp


def _category(db, name="Santexnik", slug="santexnik"):
    c = models.Category(name=name, slug=slug, is_active=True)
    db.add(c)
    db.flush()
    return c


def _order(db, customer, category, city="Toshkent", district="Yunusobod",
           status=OrderStatus.SEARCHING):
    o = models.Order(
        customer_id=customer.id,
        category_id=category.id,
        description="Test buyurtma",
        city=city,
        district=district,
        address="Test manzil",
        status=status,
        selection_mode=SelectionMode.AUTOMATIC,
    )
    db.add(o)
    db.flush()
    return o


def _offer(db, order, master, status=OfferStatus.PENDING):
    of = models.OrderOffer(
        order_id=order.id,
        master_id=master.id,
        status=status,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
    )
    db.add(of)
    db.flush()
    return of


# ====== Testlar ======


class TestAssignMasterSuccess:
    """Birinchi biriktirish muvaffaqiyatli."""

    def test_basic_assign(self, db):
        cat = _category(db)
        customer = _user(db, "+998900000001", role=Role.CUSTOMER)
        order = _order(db, customer, cat)

        # Usta 1 (g'olib bo'ladi)
        u1 = _user(db, "+998900000002", role=Role.MASTER)
        mp1 = _master(db, u1)
        offer1 = _offer(db, order, mp1)

        # Usta 2 (raqib, pending)
        u2 = _user(db, "+998900000003", role=Role.MASTER)
        mp2 = _master(db, u2)
        offer2 = _offer(db, order, mp2)

        db.commit()

        # Usta 1 o'zini biriktiradi
        result = assign_master(db, order.id, mp1.id, u1)
        db.commit()

        # Buyurtma assigned, master_id to'g'ri
        assert result.status == OrderStatus.ASSIGNED
        assert result.master_id == mp1.id

        # Tarix yozuvi bor
        history = db.scalars(
            select(models.OrderStatusHistory)
            .where(models.OrderStatusHistory.order_id == order.id)
        ).all()
        assert len(history) == 1
        assert history[0].from_status == OrderStatus.SEARCHING
        assert history[0].to_status == OrderStatus.ASSIGNED

        # G'olib taklif accepted, raqib rejected
        db.refresh(offer1)
        db.refresh(offer2)
        assert offer1.status == OfferStatus.ACCEPTED
        assert offer2.status == OfferStatus.REJECTED

    def test_admin_can_assign(self, db):
        """Admin ham usta biriktira oladi."""
        cat = _category(db)
        customer = _user(db, "+998900000001", role=Role.CUSTOMER)
        order = _order(db, customer, cat)
        admin = _user(db, "+998900000099", role=Role.ADMIN, full_name="Admin")

        u1 = _user(db, "+998900000002", role=Role.MASTER)
        mp1 = _master(db, u1)
        _offer(db, order, mp1)
        db.commit()

        result = assign_master(db, order.id, mp1.id, admin)
        db.commit()

        assert result.status == OrderStatus.ASSIGNED
        assert result.master_id == mp1.id


class TestAssignMasterConflict:
    """Ikkinchi marta biriktirish -> 409."""

    def test_double_assign_409(self, db):
        cat = _category(db)
        customer = _user(db, "+998900000001", role=Role.CUSTOMER)
        order = _order(db, customer, cat)

        u1 = _user(db, "+998900000002", role=Role.MASTER)
        mp1 = _master(db, u1)
        _offer(db, order, mp1)

        u2 = _user(db, "+998900000003", role=Role.MASTER)
        mp2 = _master(db, u2)
        _offer(db, order, mp2)
        db.commit()

        # Birinchi muvaffaqiyatli
        assign_master(db, order.id, mp1.id, u1)
        db.commit()

        # Ikkinchi -> 409
        with pytest.raises(HTTPException) as exc_info:
            assign_master(db, order.id, mp2.id, u2)
        assert exc_info.value.status_code == 409


class TestAssignMasterNonSearching:
    """Qidiruv bo'lmagan buyurtmaga biriktirish -> 409."""

    def test_cancelled_order_409(self, db):
        cat = _category(db)
        customer = _user(db, "+998900000001", role=Role.CUSTOMER)
        order = _order(db, customer, cat, status=OrderStatus.CANCELLED)

        u1 = _user(db, "+998900000002", role=Role.MASTER)
        mp1 = _master(db, u1)
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            assign_master(db, order.id, mp1.id, u1)
        assert exc_info.value.status_code == 409


class TestAssignMasterStaleSession:
    """Stale session: ikki sessiyada bir vaqtda biriktirish urinishi.

    Session A birinchi biriktiradi va commit qiladi.
    Session B hali eski holatni ko'radi (searching), lekin atomic UPDATE
    rowcount=0 qaytarishi kerak -> 409.
    """

    def test_stale_session_conflict(self, db):
        cat = _category(db)
        customer = _user(db, "+998900000001", role=Role.CUSTOMER)
        order = _order(db, customer, cat)

        u1 = _user(db, "+998900000002", role=Role.MASTER)
        mp1 = _master(db, u1)
        _offer(db, order, mp1)

        u2 = _user(db, "+998900000003", role=Role.MASTER)
        mp2 = _master(db, u2)
        _offer(db, order, mp2)
        db.commit()

        order_id = order.id

        # Session B (mustaqil) ochish
        session_b = SessionLocal()
        try:
            # Session B da buyurtmani o'qish (hali searching)
            order_b = session_b.get(models.Order, order_id)
            assert order_b.status == OrderStatus.SEARCHING

            # Session A (db fixture) da biriktirish va commit
            assign_master(db, order_id, mp1.id, u1)
            db.commit()

            # Session A muvaffaqiyatli — tasdiqlash
            db.refresh(db.get(models.Order, order_id))
            assert db.get(models.Order, order_id).status == OrderStatus.ASSIGNED

            # Session B da user2 ni qayta o'qish (chunki u2 db sessiyada yaratilgan)
            user2_b = session_b.get(models.User, u2.id)

            # Session B orqali biriktirish: atomic UPDATE rowcount = 0 -> 409
            with pytest.raises(HTTPException) as exc_info:
                assign_master(session_b, order_id, mp2.id, user2_b)
            assert exc_info.value.status_code == 409
        finally:
            session_b.rollback()
            session_b.close()


class TestAssignMasterForbidden:
    """Actor tekshiruvlari."""

    def test_customer_cannot_assign(self, db):
        """Mijoz usta biriktira olmaydi."""
        cat = _category(db)
        customer = _user(db, "+998900000001", role=Role.CUSTOMER)
        order = _order(db, customer, cat)

        u1 = _user(db, "+998900000002", role=Role.MASTER)
        mp1 = _master(db, u1)
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            assign_master(db, order.id, mp1.id, customer)
        assert exc_info.value.status_code == 403

    def test_master_cannot_assign_other(self, db):
        """Usta boshqa ustani biriktira olmaydi."""
        cat = _category(db)
        customer = _user(db, "+998900000001", role=Role.CUSTOMER)
        order = _order(db, customer, cat)

        u1 = _user(db, "+998900000002", role=Role.MASTER)
        mp1 = _master(db, u1)

        u2 = _user(db, "+998900000003", role=Role.MASTER)
        mp2 = _master(db, u2)
        db.commit()

        # u1 mp2 ni biriktirmoqchi -> 403
        with pytest.raises(HTTPException) as exc_info:
            assign_master(db, order.id, mp2.id, u1)
        assert exc_info.value.status_code == 403
