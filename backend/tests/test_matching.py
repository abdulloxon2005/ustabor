"""Matching algoritmini testlash (bayes_rating, score, rank, offer, expire, offer_next).

Barcha testlar db fixture orqali ishlaydi (HTTP yo'q).
"""

import math
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app import models
from app.core.config import settings
from app.core.security import hash_password
from app.models.enums import (
    OfferStatus,
    OrderStatus,
    PricingType,
    Role,
    SelectionMode,
)
from app.services import matching

import pytest


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


def _master(db, user, city="Toshkent", district="Yunusobod", is_approved=True, is_available=True,
            rating_avg=0.0, rating_count=0):
    mp = models.MasterProfile(
        user_id=user.id,
        city=city,
        district=district,
        is_approved=is_approved,
        is_available=is_available,
        rating_avg=rating_avg,
        rating_count=rating_count,
    )
    db.add(mp)
    db.flush()
    return mp


def _service(db, master, category):
    ms = models.MasterService(
        master_id=master.id,
        category_id=category.id,
        pricing_type=PricingType.FIXED,
        base_price=50000,
    )
    db.add(ms)
    db.flush()
    return ms


def _category(db, name="Santexnik", slug="santexnik"):
    c = models.Category(name=name, slug=slug, is_active=True)
    db.add(c)
    db.flush()
    return c


def _order(db, customer, category, city="Toshkent", district="Yunusobod"):
    o = models.Order(
        customer_id=customer.id,
        category_id=category.id,
        description="Test buyurtma",
        city=city,
        district=district,
        address="Test manzil",
        status=OrderStatus.SEARCHING,
        selection_mode=SelectionMode.AUTOMATIC,
    )
    db.add(o)
    db.flush()
    return o


# ====== bayes_rating testlari ======


class TestBayesRating:
    def test_zero_reviews_gives_global_avg(self):
        """Sharhsiz usta aynan C (global_avg) oladi."""
        assert matching.bayes_rating(0.0, 0, 4.0, m=5) == 4.0

    def test_one_five_star_vs_experienced(self):
        """1 ta 5 yulduzli sharh 50 ta 4.8 li ustadan past bo'lishi kerak."""
        newbie = matching.bayes_rating(5.0, 1, 4.0, m=5)
        veteran = matching.bayes_rating(4.8, 50, 4.0, m=5)
        assert veteran > newbie

    def test_large_count_converges_to_raw(self):
        """Ko'p sharhlar bilan Bayes o'rtacha haqiqiy o'rtachaga yaqinlashadi."""
        raw_avg = 3.5
        result = matching.bayes_rating(raw_avg, 10000, 4.0, m=5)
        assert abs(result - raw_avg) < 0.01

    def test_equal_m_and_v(self):
        """v == m bo'lganda natija (R + C) / 2 bo'ladi."""
        result = matching.bayes_rating(5.0, 5, 3.0, m=5)
        expected = (5.0 + 3.0) / 2.0
        assert abs(result - expected) < 1e-9


# ====== score_master testlari ======


class TestScoreMaster:
    def test_district_match_beats_city_only(self, db):
        """Tuman mos kelgan usta faqat shahar mos kelgandan yuqori ball oladi (reyting teng)."""
        cat = _category(db)
        customer = _user(db, "+998900000001", role=Role.CUSTOMER)
        order = _order(db, customer, cat, city="Toshkent", district="Yunusobod")

        u1 = _user(db, "+998900000002")
        m1 = _master(db, u1, city="Toshkent", district="Yunusobod",
                     rating_avg=4.0, rating_count=10)

        u2 = _user(db, "+998900000003")
        m2 = _master(db, u2, city="Toshkent", district="Chilonzor",
                     rating_avg=4.0, rating_count=10)

        db.commit()
        g_avg = 4.0
        s1 = matching.score_master(m1, order, g_avg)
        s2 = matching.score_master(m2, order, g_avg)
        assert s1 > s2

    def test_new_master_lands_in_middle(self, db):
        """Yangi usta (kam sharh) o'rtada: tajribali yuqorisidan past, pastgisidan yuqori."""
        cat = _category(db)
        customer = _user(db, "+998900000001", role=Role.CUSTOMER)
        order = _order(db, customer, cat)

        # Tajribali-yuqori: 4.9 reyting, 50 sharh
        u_top = _user(db, "+998900000002")
        m_top = _master(db, u_top, rating_avg=4.9, rating_count=50)

        # Yangi usta: 0 sharh (global_avg oladi)
        u_new = _user(db, "+998900000003")
        m_new = _master(db, u_new, rating_avg=0.0, rating_count=0)

        # Tajribali-past: 2.0 reyting, 50 sharh
        u_low = _user(db, "+998900000004")
        m_low = _master(db, u_low, rating_avg=2.0, rating_count=50)

        db.commit()
        g_avg = 4.0

        s_top = matching.score_master(m_top, order, g_avg)
        s_new = matching.score_master(m_new, order, g_avg)
        s_low = matching.score_master(m_low, order, g_avg)

        assert s_top > s_new > s_low


# ====== eligible_masters testlari ======


class TestEligibleMasters:
    def _setup(self, db):
        """Standart setup: 1 kategoriya, 1 mijoz, 1 buyurtma."""
        cat = _category(db)
        customer = _user(db, "+998900000001", role=Role.CUSTOMER)
        order = _order(db, customer, cat, city="Toshkent", district="Yunusobod")
        return cat, customer, order

    def test_basic_eligible(self, db):
        """To'g'ri usta topiladi."""
        cat, customer, order = self._setup(db)
        u = _user(db, "+998900000002")
        mp = _master(db, u, city="Toshkent", district="Yunusobod")
        _service(db, mp, cat)
        db.commit()

        result = matching.eligible_masters(db, order)
        assert len(result) == 1
        assert result[0].id == mp.id

    def test_excludes_unapproved(self, db):
        cat, customer, order = self._setup(db)
        u = _user(db, "+998900000002")
        mp = _master(db, u, is_approved=False)
        _service(db, mp, cat)
        db.commit()

        assert matching.eligible_masters(db, order) == []

    def test_excludes_unavailable(self, db):
        cat, customer, order = self._setup(db)
        u = _user(db, "+998900000002")
        mp = _master(db, u, is_available=False)
        _service(db, mp, cat)
        db.commit()

        assert matching.eligible_masters(db, order) == []

    def test_excludes_blocked_user(self, db):
        cat, customer, order = self._setup(db)
        u = _user(db, "+998900000002", is_active=False)
        mp = _master(db, u)
        _service(db, mp, cat)
        db.commit()

        assert matching.eligible_masters(db, order) == []

    def test_excludes_wrong_category(self, db):
        cat, customer, order = self._setup(db)
        other_cat = _category(db, name="Elektrik", slug="elektrik")
        u = _user(db, "+998900000002")
        mp = _master(db, u)
        _service(db, mp, other_cat)  # boshqa kategoriya
        db.commit()

        assert matching.eligible_masters(db, order) == []

    def test_excludes_other_city(self, db):
        cat, customer, order = self._setup(db)
        u = _user(db, "+998900000002")
        mp = _master(db, u, city="Samarqand", district="Yunusobod")
        _service(db, mp, cat)
        db.commit()

        assert matching.eligible_masters(db, order) == []

    def test_excludes_by_id(self, db):
        cat, customer, order = self._setup(db)
        u = _user(db, "+998900000002")
        mp = _master(db, u)
        _service(db, mp, cat)
        db.commit()

        assert matching.eligible_masters(db, order, exclude_master_ids={mp.id}) == []


# ====== rank_masters testlari ======


class TestRankMasters:
    def test_deterministic_ranking(self, db):
        """Bir xil sharoitda rank ikki marta chaqirilsa ham natija bir xil."""
        cat = _category(db)
        customer = _user(db, "+998900000001", role=Role.CUSTOMER)
        order = _order(db, customer, cat)

        masters = []
        for i in range(5):
            u = _user(db, f"+99890100{i:04d}")
            mp = _master(db, u, rating_avg=4.0, rating_count=10)
            _service(db, mp, cat)
            masters.append(mp)
        db.commit()

        ranked1 = matching.rank_masters(db, order)
        ranked2 = matching.rank_masters(db, order)
        assert [m.id for m in ranked1] == [m.id for m in ranked2]


# ====== Offer testlari ======


class TestOfferCreation:
    def test_offer_expires_in_future(self, db):
        """Yaratilgan taklif kelajakda amal qiladi."""
        cat = _category(db)
        customer = _user(db, "+998900000001", role=Role.CUSTOMER)
        order = _order(db, customer, cat)
        u = _user(db, "+998900000002")
        mp = _master(db, u)
        db.commit()

        offer = matching.create_offer(db, order, mp)
        db.flush()

        assert offer.status == OfferStatus.PENDING
        assert offer.expires_at > datetime.now(timezone.utc)


class TestExpireStaleOffers:
    def test_marks_past_due_only(self, db):
        """Faqat muddati o'tgan pending takliflarni expired qiladi."""
        cat = _category(db)
        customer = _user(db, "+998900000001", role=Role.CUSTOMER)
        order = _order(db, customer, cat)
        u1 = _user(db, "+998900000002")
        mp1 = _master(db, u1)
        u2 = _user(db, "+998900000003")
        mp2 = _master(db, u2)
        db.flush()

        # Muddati o'tgan taklif
        stale_offer = models.OrderOffer(
            order_id=order.id,
            master_id=mp1.id,
            status=OfferStatus.PENDING,
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        )
        db.add(stale_offer)

        # Hali amal qilayotgan taklif
        fresh_offer = models.OrderOffer(
            order_id=order.id,
            master_id=mp2.id,
            status=OfferStatus.PENDING,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        )
        db.add(fresh_offer)
        db.commit()

        count = matching.expire_stale_offers(db, order)
        db.commit()

        db.refresh(stale_offer)
        db.refresh(fresh_offer)
        assert count == 1
        assert stale_offer.status == OfferStatus.EXPIRED
        assert fresh_offer.status == OfferStatus.PENDING


# ====== offer_next testlari ======


class TestOfferNext:
    def test_never_offers_same_master_twice(self, db):
        """offer_next hech qachon bir ustaga ikkinchi marta taklif bermaydi."""
        cat = _category(db)
        customer = _user(db, "+998900000001", role=Role.CUSTOMER)
        order = _order(db, customer, cat)

        # 2 ta usta
        u1 = _user(db, "+998900000002")
        mp1 = _master(db, u1, rating_avg=4.5, rating_count=10)
        _service(db, mp1, cat)

        u2 = _user(db, "+998900000003")
        mp2 = _master(db, u2, rating_avg=4.0, rating_count=10)
        _service(db, mp2, cat)

        db.commit()

        offered_ids = set()

        offer1 = matching.offer_next(db, order, customer)
        assert offer1 is not None
        offered_ids.add(offer1.master_id)
        db.commit()

        offer2 = matching.offer_next(db, order, customer)
        assert offer2 is not None
        offered_ids.add(offer2.master_id)
        db.commit()

        # Har ikkalasi turli ustalar
        assert len(offered_ids) == 2

        # Uchinchi taklif None (hech kim qolmagan)
        offer3 = matching.offer_next(db, order, customer)
        assert offer3 is None

    def test_returns_none_when_no_masters(self, db):
        """Mos usta yo'q bo'lganda None qaytaradi."""
        cat = _category(db)
        customer = _user(db, "+998900000001", role=Role.CUSTOMER)
        order = _order(db, customer, cat)
        db.commit()

        result = matching.offer_next(db, order, customer)
        assert result is None

    def test_rotate_stale_automatic_orders_dispatches_next(self, db):
        """Taklif muddati o'tganda rotate_stale_automatic_orders navbatdagi ustaga taklif beradi."""
        cat = _category(db)
        customer = _user(db, "+998900000001", role=Role.CUSTOMER)
        order = _order(db, customer, cat)

        # 2 ta usta (Master A yuqori reyting, Master B pastroq)
        u1 = _user(db, "+998900000002")
        mp1 = _master(db, u1, rating_avg=4.9, rating_count=20)
        _service(db, mp1, cat)

        u2 = _user(db, "+998900000003")
        mp2 = _master(db, u2, rating_avg=4.0, rating_count=10)
        _service(db, mp2, cat)

        db.commit()

        # Dastlab Master A ga taklif
        first_offer = matching.offer_next(db, order)
        assert first_offer is not None
        assert first_offer.master_id == mp1.id
        assert first_offer.status == OfferStatus.PENDING
        db.commit()

        # Master A taklifining muddati o'tgan deb simulyatsiya qilamiz
        first_offer.expires_at = datetime.now(timezone.utc) - timedelta(minutes=10)
        db.commit()

        # rotate_stale_automatic_orders chaqirilganda:
        # 1. Master A taklifi EXPIRED bo'ladi
        # 2. Master B ga yangi PENDING taklif yuboriladi
        rotated_count = matching.rotate_stale_automatic_orders(db, order)
        db.commit()

        assert rotated_count == 1
        db.refresh(first_offer)
        assert first_offer.status == OfferStatus.EXPIRED

        # Yangi taklif Master B ga biriktirilgan
        active_offer = db.scalar(
            select(models.OrderOffer).where(
                models.OrderOffer.order_id == order.id,
                models.OrderOffer.status == OfferStatus.PENDING,
            )
        )
        assert active_offer is not None
        assert active_offer.master_id == mp2.id

        # Endi Master B ning ham muddati o'tsin
        active_offer.expires_at = datetime.now(timezone.utc) - timedelta(minutes=10)
        db.commit()

        # Qayta aylantirish: boshqa usta yo'q -> 0 qaytadi, yangi taklif bo'lmaydi
        rotated_count2 = matching.rotate_stale_automatic_orders(db, order)
        db.commit()

        assert rotated_count2 == 0
        db.refresh(active_offer)
        assert active_offer.status == OfferStatus.EXPIRED
        assert order.status == OrderStatus.SEARCHING
