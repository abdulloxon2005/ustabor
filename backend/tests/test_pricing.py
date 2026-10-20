"""pricing xizmati uchun unit testlar (HTTP yo'q, faqat db fixture)."""

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app import models
from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.enums import (
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
    PricingType,
    QuoteStatus,
    Role,
    SelectionMode,
)
from app.services import pricing
from app.services.pricing import (
    accept_quote,
    apply_fixed_price,
    complete_order,
    compute_commission,
    propose_quote,
    reject_quote,
    start_order,
)


# ====== Yordamchi funksiyalar ======


def _user(db, phone: str, role: Role = Role.CUSTOMER, full_name: str = "Test") -> models.User:
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


def _master(
    db,
    user: models.User,
    city: str = "Toshkent",
    district: str = "Chilonzor",
    is_approved: bool = True,
) -> models.MasterProfile:
    mp = models.MasterProfile(
        user_id=user.id,
        city=city,
        district=district,
        is_approved=is_approved,
    )
    db.add(mp)
    db.flush()
    db.refresh(user)
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
    status: OrderStatus = OrderStatus.ASSIGNED,
    agreed_price: int | None = None,
    commission_rate: int | None = None,
) -> models.Order:
    kwargs = dict(
        customer_id=customer.id,
        category_id=category.id,
        master_id=master.id if master else None,
        description="Kran oqyapti",
        city="Toshkent",
        district="Chilonzor",
        address="1-uy",
        status=status,
        selection_mode=SelectionMode.MANUAL,
        agreed_price=agreed_price,
    )
    if commission_rate is not None:
        kwargs["commission_rate"] = commission_rate
    o = models.Order(**kwargs)
    db.add(o)
    db.flush()
    return o


# ====== 1. compute_commission testlari ======


class TestComputeCommission:
    @pytest.mark.parametrize(
        "price,rate,expected",
        [
            (200_000, 10, 20_000),
            (150_001, 10, 15_000),
            (1, 10, 0),
            (250_000, 0, 0),
            (250_000, 100, 250_000),
        ],
    )
    def test_valid_examples(self, price, rate, expected):
         result = compute_commission(price, rate)
         assert isinstance(result, int)
         assert result == expected

    @pytest.mark.parametrize(
        "price,rate",
        [
            (0, 10),
            (-100, 10),
            (100_000, -1),
            (100_000, 101),
            (100_000.0, 10),
            (100_000, 10.5),
            (True, 10),
            (100_000, False),
            (None, 10),
            (100_000, None),
        ],
    )
    def test_invalid_values_raise(self, price, rate):
        with pytest.raises(ValueError):
            compute_commission(price, rate)


# ====== 2. propose_quote testlari ======


class TestProposeQuote:
    def test_happy_path(self, db):
        cat = _category(db)
        cust = _user(db, "+998900000001", Role.CUSTOMER)
        u_m = _user(db, "+998900000002", Role.MASTER)
        mp = _master(db, u_m)
        order = _order(db, cust, cat, master=mp, status=OrderStatus.ASSIGNED)

        q = propose_quote(db, order, mp, 180_000, "Kran va shlang almashtirish")
        assert q.id is not None
        assert q.order_id == order.id
        assert q.master_id == mp.id
        assert q.price == 180_000
        assert q.note == "Kran va shlang almashtirish"
        assert q.status == QuoteStatus.PROPOSED
        assert order.agreed_price is None

    def test_rejections_wrong_master_status_price_fixed(self, db):
        cat = _category(db)
        cust = _user(db, "+998900000001", Role.CUSTOMER)
        u_m1 = _user(db, "+998900000002", Role.MASTER)
        mp1 = _master(db, u_m1)
        u_m2 = _user(db, "+998900000003", Role.MASTER)
        mp2 = _master(db, u_m2)

        order = _order(db, cust, cat, master=mp1, status=OrderStatus.ASSIGNED)

        # Boshqa usta -> 409
        with pytest.raises(HTTPException) as exc:
            propose_quote(db, order, mp2, 100_000, "Boshqa usta")
        assert exc.value.status_code == 409

        # Buyurtma assigned emas -> 409
        searching_order = _order(db, cust, cat, master=None, status=OrderStatus.SEARCHING)
        with pytest.raises(HTTPException) as exc:
            propose_quote(db, searching_order, mp1, 100_000, "Qidiruvda")
        assert exc.value.status_code == 409

        # Narx <= 0 yoki haddan tashqari katta -> 409
        for bad_price in (0, -50_000, settings.QUOTE_MAX_PRICE + 1):
            with pytest.raises(HTTPException) as exc:
                propose_quote(db, order, mp1, bad_price, "Xato narx")
            assert exc.value.status_code == 409

        # Narx allaqachon tasdiqlangan -> 409
        fixed_order = _order(
            db, cust, cat, master=mp1, status=OrderStatus.ASSIGNED, agreed_price=150_000
        )
        with pytest.raises(HTTPException) as exc:
            propose_quote(db, fixed_order, mp1, 200_000, "Qayta narx")
        assert exc.value.status_code == 409

    def test_second_quote_supersedes_first(self, db):
        cat = _category(db)
        cust = _user(db, "+998900000001", Role.CUSTOMER)
        u_m = _user(db, "+998900000002", Role.MASTER)
        mp = _master(db, u_m)
        order = _order(db, cust, cat, master=mp, status=OrderStatus.ASSIGNED)

        q1 = propose_quote(db, order, mp, 100_000, "Birinchi taklif")
        q2 = propose_quote(db, order, mp, 150_000, "Ikkinchi taklif")
        db.commit()

        db.refresh(q1)
        db.refresh(q2)
        assert q1.status == QuoteStatus.REJECTED
        assert q2.status == QuoteStatus.PROPOSED


# ====== 3. accept_quote va reject_quote testlari ======


class TestAcceptAndRejectQuote:
    def test_accept_quote_sets_agreed_price_and_closes_other_quotes(self, db):
        cat = _category(db)
        cust = _user(db, "+998900000001", Role.CUSTOMER)
        u_m = _user(db, "+998900000002", Role.MASTER)
        mp = _master(db, u_m)
        order = _order(db, cust, cat, master=mp, status=OrderStatus.ASSIGNED)

        # Bazada 2 ta proposed quote bo'lgan holatni ham tekshiramiz
        other_q = models.Quote(
            order_id=order.id,
            master_id=mp.id,
            price=120_000,
            note="Eski",
            status=QuoteStatus.PROPOSED,
        )
        win_q = models.Quote(
            order_id=order.id,
            master_id=mp.id,
            price=160_000,
            note="Yangi",
            status=QuoteStatus.PROPOSED,
        )
        db.add_all([other_q, win_q])
        db.flush()

        accept_quote(db, order, win_q, cust)
        db.commit()

        db.refresh(order)
        db.refresh(win_q)
        db.refresh(other_q)
        assert order.agreed_price == 160_000
        assert win_q.status == QuoteStatus.ACCEPTED
        assert other_q.status == QuoteStatus.REJECTED

    def test_accepting_twice_or_after_price_exists_409(self, db):
        cat = _category(db)
        cust = _user(db, "+998900000001", Role.CUSTOMER)
        u_m = _user(db, "+998900000002", Role.MASTER)
        mp = _master(db, u_m)
        order = _order(db, cust, cat, master=mp, status=OrderStatus.ASSIGNED)

        q1 = propose_quote(db, order, mp, 200_000, "Taklif 1")
        q_extra = models.Quote(
            order_id=order.id,
            master_id=mp.id,
            price=250_000,
            note="Taklif 2",
            status=QuoteStatus.PROPOSED,
        )
        db.add(q_extra)
        db.flush()

        accept_quote(db, order, q1, cust)
        db.commit()

        # Xuddi shu quoteni ikkinchi marta tasdiqlash -> 409
        with pytest.raises(HTTPException) as exc1:
            accept_quote(db, order, q1, cust)
        assert exc1.value.status_code == 409

        # Narx tasdiqlangandan keyin boshqa quoteni tasdiqlash -> 409
        with pytest.raises(HTTPException) as exc2:
            accept_quote(db, order, q_extra, cust)
        assert exc2.value.status_code == 409
        assert order.agreed_price == 200_000

    def test_accept_quote_stale_session_conflict(self, db):
        """STALE SESSION test: ikki sessiya bir xil buyurtmani o'qiydi,
        session A birinchi taklifni qabul qilib commit qiladi,
        session B ikkinchi taklifni qabul qilmoqchi bo'ladi -> 409 va agreed_price A o'rnatganicha qoladi.
        """
        cat = _category(db)
        cust = _user(db, "+998900000001", Role.CUSTOMER)
        u_m = _user(db, "+998900000002", Role.MASTER)
        mp = _master(db, u_m)
        order = _order(db, cust, cat, master=mp, status=OrderStatus.ASSIGNED)

        q_a = models.Quote(
            order_id=order.id,
            master_id=mp.id,
            price=180_000,
            note="A taklifi",
            status=QuoteStatus.PROPOSED,
        )
        q_b = models.Quote(
            order_id=order.id,
            master_id=mp.id,
            price=240_000,
            note="B taklifi",
            status=QuoteStatus.PROPOSED,
        )
        db.add_all([q_a, q_b])
        db.commit()

        order_id = order.id
        qa_id = q_a.id
        qb_id = q_b.id
        cust_id = cust.id

        session_b = SessionLocal()
        try:
            # Session B buyurtma va ikkinchi taklifni oldindan o'qiydi (agreed_price hali None)
            order_b = session_b.get(models.Order, order_id)
            quote_b = session_b.get(models.Quote, qb_id)
            cust_b = session_b.get(models.User, cust_id)
            assert order_b.agreed_price is None
            assert quote_b.status == QuoteStatus.PROPOSED

            # Session A (db) birinchi taklifni qabul qiladi va commit qiladi
            accept_quote(db, order, q_a, cust)
            db.commit()
            assert order.agreed_price == 180_000

            # Session B endi o'zidagi stale order_b va quote_b bilan qabul qilmoqchi bo'ladi -> 409
            with pytest.raises(HTTPException) as exc:
                accept_quote(session_b, order_b, quote_b, cust_b)
            assert exc.value.status_code == 409
            assert (
                exc.value.detail
                == "Narx allaqachon tasdiqlangan yoki buyurtma holati o'zgargan"
            )
            session_b.rollback()
        finally:
            session_b.close()

        # Bazada agreed_price A o'rnatgan qiymatda qolganini tekshiramiz
        db.expire_all()
        fresh_order = db.get(models.Order, order_id)
        fresh_qa = db.get(models.Quote, qa_id)
        assert fresh_order.agreed_price == 180_000
        assert fresh_qa.status == QuoteStatus.ACCEPTED

    def test_reject_quote_lets_master_propose_again(self, db):
        cat = _category(db)
        cust = _user(db, "+998900000001", Role.CUSTOMER)
        u_m = _user(db, "+998900000002", Role.MASTER)
        mp = _master(db, u_m)
        order = _order(db, cust, cat, master=mp, status=OrderStatus.ASSIGNED)

        q1 = propose_quote(db, order, mp, 220_000, "Qimmatroq")
        reject_quote(db, order, q1, cust)
        assert q1.status == QuoteStatus.REJECTED
        assert order.agreed_price is None

        # Usta yana yangi narx taklif qila oladi va mijoz uni qabul qila oladi
        q2 = propose_quote(db, order, mp, 170_000, "Arzonlashtirilgan")
        assert q2.status == QuoteStatus.PROPOSED
        accept_quote(db, order, q2, cust)
        db.commit()

        assert order.agreed_price == 170_000
        assert q2.status == QuoteStatus.ACCEPTED


# ====== 4. apply_fixed_price testlari ======


class TestApplyFixedPrice:
    def test_sets_base_price_for_fixed_service(self, db):
        cat = _category(db)
        cust = _user(db, "+998900000001", Role.CUSTOMER)
        u_m = _user(db, "+998900000002", Role.MASTER)
        mp = _master(db, u_m)
        db.add(
            models.MasterService(
                master_id=mp.id,
                category_id=cat.id,
                pricing_type=PricingType.FIXED,
                base_price=95_000,
            )
        )
        db.flush()

        order = _order(db, cust, cat, master=mp, status=OrderStatus.ASSIGNED)
        apply_fixed_price(db, order)
        db.commit()

        assert order.agreed_price == 95_000

    def test_does_nothing_for_quote_service(self, db):
        cat = _category(db)
        cust = _user(db, "+998900000001", Role.CUSTOMER)
        u_m = _user(db, "+998900000002", Role.MASTER)
        mp = _master(db, u_m)
        db.add(
            models.MasterService(
                master_id=mp.id,
                category_id=cat.id,
                pricing_type=PricingType.QUOTE,
                base_price=None,
            )
        )
        db.flush()

        order = _order(db, cust, cat, master=mp, status=OrderStatus.ASSIGNED)
        apply_fixed_price(db, order)
        db.commit()

        assert order.agreed_price is None


# ====== 5. start_order va complete_order testlari ======


class TestStartAndCompleteOrder:
    def test_start_without_agreed_price_409(self, db):
        cat = _category(db)
        cust = _user(db, "+998900000001", Role.CUSTOMER)
        u_m = _user(db, "+998900000002", Role.MASTER)
        mp = _master(db, u_m)
        order = _order(db, cust, cat, master=mp, status=OrderStatus.ASSIGNED)

        with pytest.raises(HTTPException) as exc:
            start_order(db, order, u_m)
        assert exc.value.status_code == 409
        assert exc.value.detail == "Avval narx tasdiqlanishi kerak"
        assert order.status == OrderStatus.ASSIGNED

    def test_start_by_non_assigned_master_or_customer_rejected(self, db):
        cat = _category(db)
        cust = _user(db, "+998900000001", Role.CUSTOMER)
        u_m1 = _user(db, "+998900000002", Role.MASTER)
        mp1 = _master(db, u_m1)
        u_m2 = _user(db, "+998900000003", Role.MASTER)
        _master(db, u_m2)
        admin = _user(db, "+998900000099", Role.ADMIN)

        order = _order(
            db, cust, cat, master=mp1, status=OrderStatus.ASSIGNED, agreed_price=120_000
        )

        # Boshqa usta -> 403
        with pytest.raises(HTTPException) as exc_m:
            start_order(db, order, u_m2)
        assert exc_m.value.status_code == 403

        # Mijoz -> 403
        with pytest.raises(HTTPException) as exc_c:
            start_order(db, order, cust)
        assert exc_c.value.status_code == 403

        # Admin -> 403
        with pytest.raises(HTTPException) as exc_a:
            start_order(db, order, admin)
        assert exc_a.value.status_code == 403

        # Anonim -> 403
        with pytest.raises(HTTPException) as exc_anon:
            start_order(db, order, None)
        assert exc_anon.value.status_code == 403

        assert order.status == OrderStatus.ASSIGNED

    def test_complete_order_creates_payment_and_commission_and_is_idempotent(self, db):
        cat = _category(db)
        cust = _user(db, "+998900000001", Role.CUSTOMER)
        u_m = _user(db, "+998900000002", Role.MASTER)
        mp = _master(db, u_m)
        order = _order(
            db,
            cust,
            cat,
            master=mp,
            status=OrderStatus.ASSIGNED,
            agreed_price=200_000,
            commission_rate=10,
        )

        start_order(db, order, u_m)
        assert order.status == OrderStatus.IN_PROGRESS

        complete_order(db, order, u_m)
        db.commit()

        assert order.status == OrderStatus.COMPLETED
        assert order.commission_amount == 20_000

        payments = db.scalars(
            select(models.Payment).where(models.Payment.order_id == order.id)
        ).all()
        assert len(payments) == 1
        assert payments[0].amount == 200_000
        assert payments[0].method == PaymentMethod.CASH
        assert payments[0].status == PaymentStatus.PAID

        # Ikkinchi marta complete -> 409, ikkinchi Payment yaratilmaydi, komissiya o'zgarmaydi
        with pytest.raises(HTTPException) as exc:
            complete_order(db, order, u_m)
        assert exc.value.status_code == 409

        count = db.scalar(
            select(func.count())
            .select_from(models.Payment)
            .where(models.Payment.order_id == order.id)
        )
        assert count == 1
        assert order.commission_amount == 20_000

    def test_stored_commission_rate_used_when_settings_changed(self, db, monkeypatch):
        cat = _category(db)
        cust = _user(db, "+998900000001", Role.CUSTOMER)
        u_m = _user(db, "+998900000002", Role.MASTER)
        mp = _master(db, u_m)

        # Buyurtma 10% komissiya bilan yaratiladi
        order = _order(
            db,
            cust,
            cat,
            master=mp,
            status=OrderStatus.ASSIGNED,
            agreed_price=200_000,
            commission_rate=10,
        )
        assert order.commission_rate == 10

        # Keyinchalik settings.COMMISSION_RATE 15 ga o'zgaradi
        monkeypatch.setattr(settings, "COMMISSION_RATE", 15)
        assert settings.COMMISSION_RATE == 15

        start_order(db, order, u_m)
        complete_order(db, order, u_m)
        db.commit()

        # Hisobda settings (15%) emas, buyurtmada saqlangan 10% ishlatilishi shart
        assert order.commission_rate == 10
        assert order.commission_amount == 20_000

    def test_functions_do_not_commit(self, db):
        cat = _category(db)
        cust = _user(db, "+998900000001", Role.CUSTOMER)
        u_m = _user(db, "+998900000002", Role.MASTER)
        mp = _master(db, u_m)
        order = _order(db, cust, cat, master=mp, status=OrderStatus.ASSIGNED)
        db.commit()

        q = propose_quote(db, order, mp, 100_000, "Test")
        accept_quote(db, order, q, cust)
        start_order(db, order, u_m)
        complete_order(db, order, u_m)

        # Rollback hamma o'zgarishlarni bekor qilishi kerak
        db.rollback()
        db.refresh(order)
        assert order.status == OrderStatus.ASSIGNED
        assert order.agreed_price is None
        assert order.commission_amount is None
        assert pricing is not None


# ====== 6. Review fixes testlari ======


class TestReviewFixes:
    def test_stale_complete_concurrent_returns_409_and_single_payment(self, db):
        """1. STALE complete: ikki sessiya bir xil in_progress buyurtmani oladi;
        sessiya A complete qilib commit qiladi; sessiya B complete qilmoqchi bo'ladi -> 409,
        aniq bitta Payment, komissiya o'zgarmagan.
        """
        cat = _category(db)
        cust = _user(db, "+998900000021", Role.CUSTOMER)
        u_m = _user(db, "+998900000022", Role.MASTER)
        mp = _master(db, u_m)
        order = _order(
            db,
            cust,
            cat,
            master=mp,
            status=OrderStatus.IN_PROGRESS,
            agreed_price=200_000,
            commission_rate=10,
        )
        db.commit()

        order_id = order.id
        master_user_id = u_m.id

        session_b = SessionLocal()
        try:
            order_b = session_b.get(models.Order, order_id)
            user_b = session_b.get(models.User, master_user_id)
            assert order_b.status == OrderStatus.IN_PROGRESS

            # Sessiya A ishni yakunlaydi va commit qiladi
            complete_order(db, order, u_m)
            db.commit()

            assert order.status == OrderStatus.COMPLETED
            assert order.commission_amount == 20_000

            # Sessiya B stale order_b bilan yakunlamoqchi bo'ladi -> 409
            with pytest.raises(HTTPException) as exc:
                complete_order(session_b, order_b, user_b)
            assert exc.value.status_code == 409
            session_b.rollback()
        finally:
            session_b.close()

        # Bazada aynan bitta to'lov va o'zgarmagan komissiya
        db.expire_all()
        fresh = db.get(models.Order, order_id)
        assert fresh.status == OrderStatus.COMPLETED
        assert fresh.commission_amount == 20_000
        payments = db.scalars(
            select(models.Payment).where(models.Payment.order_id == order_id)
        ).all()
        assert len(payments) == 1
        assert payments[0].amount == 200_000

    def test_cancel_vs_complete_stale_cancel_rejected(self, db):
        """2. Cancel vs complete: assigned buyurtma; usta sessiya A da boshlaydi va yakunlaydi (commit);
        mijozning stale sessiyasi B bekor qilmoqchi bo'ladi -> 409 va buyurtma to'lovi bilan completed qoladi.
        """
        from app.services.order_flow import transition

        cat = _category(db)
        cust = _user(db, "+998900000023", Role.CUSTOMER)
        u_m = _user(db, "+998900000024", Role.MASTER)
        mp = _master(db, u_m)
        order = _order(
            db,
            cust,
            cat,
            master=mp,
            status=OrderStatus.ASSIGNED,
            agreed_price=150_000,
            commission_rate=10,
        )
        db.commit()

        order_id = order.id
        cust_id = cust.id

        session_b = SessionLocal()
        try:
            # Stale mijoz sessiyasi buyurtma ASSIGNED paytida yuklaydi
            order_b = session_b.get(models.Order, order_id)
            cust_b = session_b.get(models.User, cust_id)
            assert order_b.status == OrderStatus.ASSIGNED

            # Usta sessiya A da boshlaydi va yakunlaydi
            start_order(db, order, u_m)
            complete_order(db, order, u_m)
            db.commit()

            assert order.status == OrderStatus.COMPLETED

            # Mijoz stale sessiya B da bekor qilmoqchi bo'ladi -> 409
            with pytest.raises(HTTPException) as exc:
                transition(session_b, order_b, OrderStatus.CANCELLED, cust_b)
            assert exc.value.status_code == 409
            session_b.rollback()
        finally:
            session_b.close()

        # Buyurtma completed holatida to'lovi bilan qolganini tekshirish
        db.expire_all()
        fresh = db.get(models.Order, order_id)
        assert fresh.status == OrderStatus.COMPLETED
        assert fresh.commission_amount == 15_000
        payments = db.scalars(
            select(models.Payment).where(models.Payment.order_id == order_id)
        ).all()
        assert len(payments) == 1

    def test_cancel_vs_start_stale_start_rejected(self, db):
        """3. Cancel vs start: mijoz sessiya A da bekor qiladi (commit);
        ustaning stale sessiyasi B boshlamoqchi bo'ladi -> 409, buyurtma bekor qilingancha qoladi.
        """
        from app.services.order_flow import transition

        cat = _category(db)
        cust = _user(db, "+998900000025", Role.CUSTOMER)
        u_m = _user(db, "+998900000026", Role.MASTER)
        mp = _master(db, u_m)
        order = _order(
            db,
            cust,
            cat,
            master=mp,
            status=OrderStatus.ASSIGNED,
            agreed_price=100_000,
            commission_rate=10,
        )
        db.commit()

        order_id = order.id
        master_user_id = u_m.id

        session_b = SessionLocal()
        try:
            order_b = session_b.get(models.Order, order_id)
            master_b = session_b.get(models.User, master_user_id)
            assert order_b.status == OrderStatus.ASSIGNED

            # Mijoz sessiya A da bekor qiladi
            transition(db, order, OrderStatus.CANCELLED, cust)
            db.commit()

            assert order.status == OrderStatus.CANCELLED

            # Usta stale sessiya B da boshlamoqchi bo'ladi -> 409
            with pytest.raises(HTTPException) as exc:
                start_order(session_b, order_b, master_b)
            assert exc.value.status_code == 409
            session_b.rollback()
        finally:
            session_b.close()

        # Buyurtma bekor qilingan holatda qolganini tekshirish
        db.expire_all()
        fresh = db.get(models.Order, order_id)
        assert fresh.status == OrderStatus.CANCELLED

    def test_old_rejected_quote_accept_raises_409_and_accepting_active_works(self, db):
        """4. Old/rejected quote: usta 1-taklif, so'ng 2-taklif beradi (1-taklif rejected bo'ladi);
        mijoz 1-taklifni qabul qilmoqchi bo'ladi -> 409; 2-taklifni qabul qilish ishlaydi;
        agreed_price 2-taklif narxiga teng bo'ladi.
        """
        cat = _category(db)
        cust = _user(db, "+998900000027", Role.CUSTOMER)
        u_m = _user(db, "+998900000028", Role.MASTER)
        mp = _master(db, u_m)
        order = _order(db, cust, cat, master=mp, status=OrderStatus.ASSIGNED)

        q1 = propose_quote(db, order, mp, 120_000, "1-taklif")
        q2 = propose_quote(db, order, mp, 180_000, "2-taklif")
        db.commit()

        db.refresh(q1)
        db.refresh(q2)
        assert q1.status == QuoteStatus.REJECTED
        assert q2.status == QuoteStatus.PROPOSED

        # Mijoz eski rad etilgan taklifni qabul qilmoqchi bo'ladi -> 409
        with pytest.raises(HTTPException) as exc:
            accept_quote(db, order, q1, cust)
        assert exc.value.status_code == 409
        assert "taklif qilingan" in exc.value.detail.lower()

        # 2-faol taklifni qabul qilish muvaffaqiyatli ishlaydi
        accept_quote(db, order, q2, cust)
        db.commit()

        db.refresh(order)
        db.refresh(q2)
        assert order.agreed_price == 180_000
        assert q2.status == QuoteStatus.ACCEPTED

    def test_failed_order_update_does_not_leave_accepted_quote_after_rollback(self, db):
        """5. Failed order update must not leave an accepted quote behind:
        buyurtmada agreed_price allaqachon mavjud bo'lgan holat simulyatsiya qilinadi;
        proposed kotirovka uchun accept_quote chaqiriladi -> 409;
        rollback/yangi sessiyadan keyin bu kotirovka hali ham 'proposed' holatida qoladi.
        """
        cat = _category(db)
        cust = _user(db, "+998900000029", Role.CUSTOMER)
        u_m = _user(db, "+998900000030", Role.MASTER)
        mp = _master(db, u_m)
        order = _order(
            db,
            cust,
            cat,
            master=mp,
            status=OrderStatus.ASSIGNED,
            agreed_price=100_000,
        )
        q = models.Quote(
            order_id=order.id,
            master_id=mp.id,
            price=150_000,
            status=QuoteStatus.PROPOSED,
        )
        db.add(q)
        db.commit()

        # accept_quote chaqiriladi -> buyurtmada narx borligi uchun 409
        with pytest.raises(HTTPException) as exc:
            accept_quote(db, order, q, cust)
        assert exc.value.status_code == 409
        # Chaqiruvchi xatolikda rollback qiladi
        db.rollback()

        # Rollback dan so'ng kotirovka PROPOSED bo'lib qolishi shart
        db.expire_all()
        fresh_q = db.get(models.Quote, q.id)
        assert fresh_q.status == QuoteStatus.PROPOSED

    def test_apply_fixed_price_on_cancelled_and_completed_order_does_nothing(self, db):
        """6. apply_fixed_price bekor qilingan yoki yakunlangan buyurtmada hech narsa qilmaydi
        (agreed_price null yoki o'zgarmay qoladi).
        """
        cat = _category(db)
        cust = _user(db, "+998900000031", Role.CUSTOMER)
        u_m = _user(db, "+998900000032", Role.MASTER)
        mp = _master(db, u_m)
        db.add(
            models.MasterService(
                master_id=mp.id,
                category_id=cat.id,
                pricing_type=PricingType.FIXED,
                base_price=250_000,
            )
        )
        db.flush()

        # Bekor qilingan buyurtma
        cancelled_order = _order(
            db, cust, cat, master=mp, status=OrderStatus.CANCELLED, agreed_price=None
        )
        apply_fixed_price(db, cancelled_order)
        db.commit()
        db.refresh(cancelled_order)
        assert cancelled_order.agreed_price is None

        # Yakunlangan buyurtma (oldindan narxi bor)
        completed_order = _order(
            db, cust, cat, master=mp, status=OrderStatus.COMPLETED, agreed_price=200_000
        )
        apply_fixed_price(db, completed_order)
        db.commit()
        db.refresh(completed_order)
        assert completed_order.agreed_price == 200_000
