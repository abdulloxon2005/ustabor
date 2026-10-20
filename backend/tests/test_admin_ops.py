"""Unit testlar: admin_ops xizmati (admin_assign_master, set_user_active, commissions_report)."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app import models
from app.core.security import create_access_token, hash_password
from app.db.session import SessionLocal
from app.models.enums import (
    OfferStatus,
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
    PricingType,
    Role,
    SelectionMode,
)
from app.services import order_flow
from app.services.admin_ops import (
    admin_assign_master,
    commissions_report,
    set_user_active,
)


def _user(db, phone: str, role: Role = Role.CUSTOMER, full_name: str = "Test User", is_active: bool = True) -> models.User:
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


def _master(
    db,
    user: models.User,
    city: str = "Toshkent",
    district: str = "Chilonzor",
    is_approved: bool = True,
    is_available: bool = True,
) -> models.MasterProfile:
    mp = models.MasterProfile(
        user_id=user.id,
        city=city,
        district=district,
        is_approved=is_approved,
        is_available=is_available,
    )
    db.add(mp)
    db.flush()
    return mp


def _service(
    db,
    master: models.MasterProfile,
    category: models.Category,
    pricing_type: PricingType = PricingType.FIXED,
    base_price: int = 120_000,
) -> models.MasterService:
    ms = models.MasterService(
        master_id=master.id,
        category_id=category.id,
        pricing_type=pricing_type,
        base_price=base_price,
    )
    db.add(ms)
    db.flush()
    return ms


def _category(db, name: str = "Santexnik", slug: str = "santexnik") -> models.Category:
    c = models.Category(name=name, slug=slug, is_active=True)
    db.add(c)
    db.flush()
    return c


def _order(
    db,
    customer: models.User,
    category: models.Category,
    status: OrderStatus = OrderStatus.SEARCHING,
    commission_rate: int = 10,
    agreed_price: int | None = None,
) -> models.Order:
    o = models.Order(
        customer_id=customer.id,
        category_id=category.id,
        description="Admin ops test buyurtma",
        city="Toshkent",
        district="Chilonzor",
        address="Test ko'chasi 5-uy",
        status=status,
        selection_mode=SelectionMode.AUTOMATIC,
        commission_rate=commission_rate,
        agreed_price=agreed_price,
    )
    db.add(o)
    db.flush()
    return o


# ==================== admin_assign_master ====================


def test_admin_assign_master_happy_path(db):
    """Admin usta biriktiradi: assigned holat, master_id, tarix admin nomidan,
    accepted taklif va fixed narx o'rnatiladi."""
    cat = _category(db)
    cust = _user(db, "+998901000001", Role.CUSTOMER)
    admin = _user(db, "+998901000002", Role.ADMIN, full_name="Bosh Admin")
    m_user = _user(db, "+998901000003", Role.MASTER, full_name="Usta Alisher")
    mp = _master(db, m_user)
    _service(db, mp, cat, pricing_type=PricingType.FIXED, base_price=150_000)

    order = _order(db, cust, cat, status=OrderStatus.SEARCHING)

    res = admin_assign_master(db, order.id, mp.id, admin)
    db.flush()

    assert res.status == OrderStatus.ASSIGNED
    assert res.master_id == mp.id
    assert res.agreed_price == 150_000

    # Tarix admin nomidan yozilgan
    hist = db.scalars(
        select(models.OrderStatusHistory).where(models.OrderStatusHistory.order_id == order.id)
    ).all()
    assert len(hist) == 1
    assert hist[0].from_status == OrderStatus.SEARCHING
    assert hist[0].to_status == OrderStatus.ASSIGNED
    assert hist[0].changed_by == admin.id

    # OrderOffer mavjud va ACCEPTED
    offer = db.scalar(
        select(models.OrderOffer).where(
            models.OrderOffer.order_id == order.id,
            models.OrderOffer.master_id == mp.id,
        )
    )
    assert offer is not None
    assert offer.status == OfferStatus.ACCEPTED


def test_admin_assign_master_preexisting_offers(db):
    """Mavjud pending taklif accepted bo'ladi, boshqa pending taklif rejected bo'ladi."""
    cat = _category(db)
    cust = _user(db, "+998901000011", Role.CUSTOMER)
    admin = _user(db, "+998901000012", Role.ADMIN)

    m1_user = _user(db, "+998901000013", Role.MASTER)
    mp1 = _master(db, m1_user)
    _service(db, mp1, cat)

    m2_user = _user(db, "+998901000014", Role.MASTER)
    mp2 = _master(db, m2_user)
    _service(db, mp2, cat)

    order = _order(db, cust, cat, status=OrderStatus.SEARCHING)

    offer1 = models.OrderOffer(order_id=order.id, master_id=mp1.id, status=OfferStatus.PENDING)
    offer2 = models.OrderOffer(order_id=order.id, master_id=mp2.id, status=OfferStatus.PENDING)
    db.add_all([offer1, offer2])
    db.flush()

    admin_assign_master(db, order.id, mp1.id, admin)
    db.flush()

    db.refresh(offer1)
    db.refresh(offer2)
    assert offer1.status == OfferStatus.ACCEPTED
    assert offer2.status == OfferStatus.REJECTED


def test_admin_assign_master_quote_type_leaves_agreed_price_none(db):
    """Quote xizmat turida agreed_price bo'sh qoladi."""
    cat = _category(db)
    cust = _user(db, "+998901000021", Role.CUSTOMER)
    admin = _user(db, "+998901000022", Role.ADMIN)
    m_user = _user(db, "+998901000023", Role.MASTER)
    mp = _master(db, m_user)
    _service(db, mp, cat, pricing_type=PricingType.QUOTE, base_price=None)

    order = _order(db, cust, cat, status=OrderStatus.SEARCHING)

    res = admin_assign_master(db, order.id, mp.id, admin)
    db.flush()

    assert res.status == OrderStatus.ASSIGNED
    assert res.agreed_price is None


def test_admin_assign_master_already_assigned_or_cancelled_409(db):
    """Assigned yoki cancelled buyurtmaga biriktirish 409 beradi."""
    cat = _category(db)
    cust = _user(db, "+998901000031", Role.CUSTOMER)
    admin = _user(db, "+998901000032", Role.ADMIN)
    m_user = _user(db, "+998901000033", Role.MASTER)
    mp = _master(db, m_user)
    _service(db, mp, cat)

    for st in [OrderStatus.ASSIGNED, OrderStatus.CANCELLED, OrderStatus.COMPLETED]:
        order = _order(db, cust, cat, status=st)
        with pytest.raises(HTTPException) as exc_info:
            admin_assign_master(db, order.id, mp.id, admin)
        assert exc_info.value.status_code == 409


def test_admin_assign_master_second_attempt_409(db):
    """Ikkinchi biriktirish urinishi 409 beradi."""
    cat = _category(db)
    cust = _user(db, "+998901000041", Role.CUSTOMER)
    admin = _user(db, "+998901000042", Role.ADMIN)
    m_user = _user(db, "+998901000043", Role.MASTER)
    mp = _master(db, m_user)
    _service(db, mp, cat)

    order = _order(db, cust, cat, status=OrderStatus.SEARCHING)
    admin_assign_master(db, order.id, mp.id, admin)
    db.flush()

    with pytest.raises(HTTPException) as exc_info:
        admin_assign_master(db, order.id, mp.id, admin)
    assert exc_info.value.status_code == 409


def test_admin_assign_master_ineligible_master_rejected(db):
    """Tasdiqlanmagan, band, foydalanuvchisi bloklangan yoki toifasi yo'q usta rad etiladi."""
    cat1 = _category(db, name="Santexnik", slug="santexnik-1")
    cat2 = _category(db, name="Elektrik", slug="elektrik-1")
    cust = _user(db, "+998901000051", Role.CUSTOMER)
    admin = _user(db, "+998901000052", Role.ADMIN)

    order = _order(db, cust, cat1, status=OrderStatus.SEARCHING)

    # 1. Unapproved
    u1 = _user(db, "+998901000053", Role.MASTER)
    mp1 = _master(db, u1, is_approved=False)
    _service(db, mp1, cat1)
    with pytest.raises(HTTPException) as exc_info:
        admin_assign_master(db, order.id, mp1.id, admin)
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Usta tasdiqlanmagan"

    # 2. Unavailable
    u2 = _user(db, "+998901000054", Role.MASTER)
    mp2 = _master(db, u2, is_available=False)
    _service(db, mp2, cat1)
    with pytest.raises(HTTPException) as exc_info:
        admin_assign_master(db, order.id, mp2.id, admin)
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Usta band yoki faol emas"

    # 3. Blocked user
    u3 = _user(db, "+998901000055", Role.MASTER, is_active=False)
    mp3 = _master(db, u3)
    _service(db, mp3, cat1)
    with pytest.raises(HTTPException) as exc_info:
        admin_assign_master(db, order.id, mp3.id, admin)
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Usta foydalanuvchisi faol emas"

    # 4. Wrong category (faqat Elektrik xizmati bor)
    u4 = _user(db, "+998901000056", Role.MASTER)
    mp4 = _master(db, u4)
    _service(db, mp4, cat2)
    with pytest.raises(HTTPException) as exc_info:
        admin_assign_master(db, order.id, mp4.id, admin)
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Usta ushbu toifadagi xizmatni ko'rsatmaydi"


def test_admin_assign_master_city_check(db):
    """Boshqa shahardagi ustani biriktirish -> 409 va buyurtma searching holatida qoladi;
    xuddi shu shahar harf katta-kichikligi yoki bo'shliqlar bilan farq qilsa -> ishlaydi."""
    cat = _category(db, name="Santexnik", slug="santexnik-city")
    cust = _user(db, "+998901000081", Role.CUSTOMER)
    admin = _user(db, "+998901000082", Role.ADMIN)

    order = _order(db, cust, cat, status=OrderStatus.SEARCHING)  # city="Toshkent"

    # Samarqandlik usta (qolgan barcha shartlarga mos) -> 409
    u_sam = _user(db, "+998901000083", Role.MASTER)
    mp_sam = _master(db, u_sam, city="Samarkand")
    _service(db, mp_sam, cat)

    with pytest.raises(HTTPException) as exc_info:
        admin_assign_master(db, order.id, mp_sam.id, admin)
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Usta boshqa shaharda joylashgan"

    db.refresh(order)
    assert order.status == OrderStatus.SEARCHING
    assert order.master_id is None

    # Harf katta-kichikligi va bo'shliqlar bilan farq qiluvchi bir xil shahar -> 200/assigned
    u_tosh = _user(db, "+998901000084", Role.MASTER)
    mp_tosh = _master(db, u_tosh, city="  tOShKeNt  ")
    _service(db, mp_tosh, cat)

    res = admin_assign_master(db, order.id, mp_tosh.id, admin)
    db.flush()
    assert res.status == OrderStatus.ASSIGNED
    assert res.master_id == mp_tosh.id


def test_admin_assign_master_non_admin_forbidden(db):
    """Admin bo'lmagan foydalanuvchi biriktira olmaydi (403)."""
    cat = _category(db)
    cust = _user(db, "+998901000061", Role.CUSTOMER)
    m_user = _user(db, "+998901000062", Role.MASTER)
    mp = _master(db, m_user)
    _service(db, mp, cat)
    order = _order(db, cust, cat, status=OrderStatus.SEARCHING)

    with pytest.raises(HTTPException) as exc_info:
        admin_assign_master(db, order.id, mp.id, cust)
    assert exc_info.value.status_code == 403

    with pytest.raises(HTTPException) as exc_info:
        admin_assign_master(db, order.id, mp.id, m_user)
    assert exc_info.value.status_code == 403


def test_admin_assign_master_stale_session_conflict(db):
    """Stale sessiya: usta A sessiyada qabul qiladi, admin B eski sessiyada biriktirganda 409 oladi."""
    cat = _category(db)
    cust = _user(db, "+998901000071", Role.CUSTOMER)
    admin = _user(db, "+998901000072", Role.ADMIN)

    m1_user = _user(db, "+998901000073", Role.MASTER)
    mp1 = _master(db, m1_user)
    _service(db, mp1, cat)

    m2_user = _user(db, "+998901000074", Role.MASTER)
    mp2 = _master(db, m2_user)
    _service(db, mp2, cat)

    order = _order(db, cust, cat, status=OrderStatus.SEARCHING)
    offer1 = models.OrderOffer(order_id=order.id, master_id=mp1.id, status=OfferStatus.PENDING)
    db.add(offer1)
    db.commit()

    order_id = order.id
    admin_id = admin.id

    session_b = SessionLocal()
    try:
        # Session B buyurtmani SEARCHING holatida o'qiydi
        order_b = session_b.get(models.Order, order_id)
        admin_b = session_b.get(models.User, admin_id)
        assert order_b.status == OrderStatus.SEARCHING

        # Session A da usta 1 qabul qiladi va commit bo'ladi
        order_flow.assign_master(db, order_id, mp1.id, actor=m1_user)
        db.commit()

        # Session B da admin usta 2 ni biriktirishga urinadi -> 409
        with pytest.raises(HTTPException) as exc_info:
            admin_assign_master(session_b, order_id, mp2.id, admin_b)
        assert exc_info.value.status_code == 409
    finally:
        session_b.close()


# ==================== set_user_active ====================


def test_set_user_active_blocks_customer_and_master(db):
    """Admin mijoz va ustani bloklay oladi va blokdan chiqara oladi."""
    admin = _user(db, "+998902000001", Role.ADMIN)
    cust = _user(db, "+998902000002", Role.CUSTOMER)
    m_user = _user(db, "+998902000003", Role.MASTER)

    # Bloklash
    set_user_active(db, cust.id, is_active=False, admin=admin)
    set_user_active(db, m_user.id, is_active=False, admin=admin)
    db.flush()

    assert cust.is_active is False
    assert m_user.is_active is False

    # Qayta faollashtirish
    set_user_active(db, cust.id, is_active=True, admin=admin)
    db.flush()
    assert cust.is_active is True


def test_set_user_active_refuses_admins_and_self(db):
    """Admin o'zini yoki boshqa adminni bloklay olmaydi (409)."""
    admin1 = _user(db, "+998902000011", Role.ADMIN)
    admin2 = _user(db, "+998902000012", Role.ADMIN)

    # O'zini bloklash
    with pytest.raises(HTTPException) as exc_info:
        set_user_active(db, admin1.id, is_active=False, admin=admin1)
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Adminni bloklab bo'lmaydi"

    # Boshqa adminni bloklash
    with pytest.raises(HTTPException) as exc_info:
        set_user_active(db, admin2.id, is_active=False, admin=admin1)
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Adminni bloklab bo'lmaydi"


def test_set_user_active_unknown_user_404(db):
    """Noma'lum foydalanuvchi 404 beradi."""
    admin = _user(db, "+998902000021", Role.ADMIN)
    with pytest.raises(HTTPException) as exc_info:
        set_user_active(db, 999999, is_active=False, admin=admin)
    assert exc_info.value.status_code == 404


def test_set_user_active_non_admin_forbidden(db):
    """Oddiy foydalanuvchi boshqalarni bloklay olmaydi (403)."""
    cust1 = _user(db, "+998902000031", Role.CUSTOMER)
    cust2 = _user(db, "+998902000032", Role.CUSTOMER)
    with pytest.raises(HTTPException) as exc_info:
        set_user_active(db, cust2.id, is_active=False, admin=cust1)
    assert exc_info.value.status_code == 403


def test_blocked_user_existing_token_stops_working(client, db):
    """Bloklangan foydalanuvchining avvalgi tokeni /auth/me da 401 beradi."""
    admin = _user(db, "+998902000041", Role.ADMIN)
    cust = _user(db, "+998902000042", Role.CUSTOMER)
    db.commit()

    token = create_access_token(cust.id)
    headers = {"Authorization": f"Bearer {token}"}

    # Bloklashdan oldin ishlaydi
    r = client.get("/api/v1/auth/me", headers=headers)
    assert r.status_code == 200

    # Admin bloklaydi
    set_user_active(db, cust.id, is_active=False, admin=admin)
    db.commit()

    # Bloklangandan so'ng token 401 beradi
    r = client.get("/api/v1/auth/me", headers=headers)
    assert r.status_code == 401
    assert r.json()["detail"] == "Avtorizatsiya talab qilinadi"


# ==================== commissions_report ====================


def test_commissions_report_hand_computed_case(db):
    """Ikki yakunlangan buyurtma (10% va 15% komissiya) va yakunlanmaganlarni hisobga olmaslik.

    Buyurtma 1: agreed_price=100_000, commission_rate=10 -> commission_amount=10_000, net=90_000.
    Buyurtma 2: agreed_price=200_000, commission_rate=15 -> commission_amount=30_000, net=170_000.
    Jami: total=2, gross=300_000, commission=40_000.
    """
    cat = _category(db, name="Ta'mirlash", slug="tamirlash")
    cust = _user(db, "+998903000001", Role.CUSTOMER)
    m_user = _user(db, "+998903000002", Role.MASTER, full_name="Usta Komil")
    mp = _master(db, m_user)

    now = datetime.now(timezone.utc)

    # 1-buyurtma: completed, rate 10%
    o1 = _order(db, cust, cat, status=OrderStatus.COMPLETED, commission_rate=10, agreed_price=100_000)
    o1.master_id = mp.id
    o1.commission_amount = 10_000
    h1 = models.OrderStatusHistory(
        order_id=o1.id,
        from_status=OrderStatus.IN_PROGRESS,
        to_status=OrderStatus.COMPLETED,
        created_at=now - timedelta(hours=2),
    )
    p1 = models.Payment(
        order_id=o1.id,
        method=PaymentMethod.CASH,
        amount=100_000,
        status=PaymentStatus.PAID,
    )
    db.add_all([h1, p1])

    # 2-buyurtma: completed, rate 15%
    o2 = _order(db, cust, cat, status=OrderStatus.COMPLETED, commission_rate=15, agreed_price=200_000)
    o2.master_id = mp.id
    o2.commission_amount = 30_000
    h2 = models.OrderStatusHistory(
        order_id=o2.id,
        from_status=OrderStatus.IN_PROGRESS,
        to_status=OrderStatus.COMPLETED,
        created_at=now - timedelta(hours=1),
    )
    p2 = models.Payment(
        order_id=o2.id,
        method=PaymentMethod.CASH,
        amount=200_000,
        status=PaymentStatus.PAID,
    )
    db.add_all([h2, p2])

    # Yakunlanmagan buyurtmalar (hisobotga kirmasligi kerak)
    o3 = _order(db, cust, cat, status=OrderStatus.SEARCHING, agreed_price=500_000)
    o4 = _order(db, cust, cat, status=OrderStatus.CANCELLED, agreed_price=50_000)
    o5 = _order(db, cust, cat, status=OrderStatus.IN_PROGRESS, agreed_price=80_000)
    db.flush()

    report = commissions_report(db)

    # Totals tekshiruvi (ham dict, ham atribut, ham tuple unpacking orqali)
    assert report.total_completed_orders == 2
    assert report.gross_total == 300_000
    assert report.commission_total == 40_000
    assert len(report.orders) == 2

    tot, gross, comm, items = report
    assert tot == 2
    assert gross == 300_000
    assert comm == 40_000

    # Tartib: newest first (o2 oldin, o1 keyin)
    first_item = report.orders[0]
    second_item = report.orders[1]

    assert first_item.id == o2.id
    assert first_item.category_name == "Ta'mirlash"
    assert first_item.master_name == "Usta Komil"
    assert first_item.agreed_price == 200_000
    assert first_item.commission_rate == 15
    assert first_item.commission_amount == 30_000
    assert first_item.master_net == 170_000
    assert first_item.payment_amount == 200_000
    assert first_item.payment_status == "paid"

    assert second_item.id == o1.id
    assert second_item.agreed_price == 100_000
    assert second_item.commission_rate == 10
    assert second_item.commission_amount == 10_000
    assert second_item.master_net == 90_000
    assert second_item.payment_amount == 100_000


def test_commissions_report_date_filtering_and_pagination(db):
    """Sana filtri (date_from / date_to) va sahifalash (limit / offset)."""
    cat = _category(db)
    cust = _user(db, "+998903000011", Role.CUSTOMER)
    m_user = _user(db, "+998903000012", Role.MASTER)
    mp = _master(db, m_user)

    base_time = datetime(2026, 10, 15, 12, 0, 0)

    # 3 ta turli kunda yakunlangan buyurtma
    orders = []
    for i in range(3):
        o = _order(db, cust, cat, status=OrderStatus.COMPLETED, agreed_price=100_000 * (i + 1))
        o.master_id = mp.id
        o.commission_amount = 10_000 * (i + 1)
        h = models.OrderStatusHistory(
            order_id=o.id,
            from_status=OrderStatus.IN_PROGRESS,
            to_status=OrderStatus.COMPLETED,
            created_at=base_time + timedelta(days=i),
        )
        db.add(h)
        orders.append(o)
    db.flush()

    # 1. Hammasi (filtrlarsiz)
    r_all = commissions_report(db)
    assert r_all.total_completed_orders == 3
    assert r_all.gross_total == 600_000

    # 2. Faqat 16-oktabrdan boshlab (i=1 va i=2)
    r_filtered = commissions_report(db, date_from=datetime(2026, 10, 16, 0, 0, 0))
    assert r_filtered.total_completed_orders == 2
    assert r_filtered.gross_total == 500_000
    assert len(r_filtered.orders) == 2

    # 3. Faqat 15-oktabr (i=0)
    r_single_day = commissions_report(
        db,
        date_from=datetime(2026, 10, 15, 0, 0, 0),
        date_to=datetime(2026, 10, 15, 23, 59, 59),
    )
    assert r_single_day.total_completed_orders == 1
    assert r_single_day.gross_total == 100_000

    # 4. Sahifalash: limit=1, offset=1
    r_paged = commissions_report(db, limit=1, offset=1)
    assert r_paged.total_completed_orders == 3  # Jami o'zgarmaydi
    assert len(r_paged.orders) == 1
    assert r_paged.orders[0].id == orders[1].id
