"""Narx takliflari (quotes), qat'iy narx, ishni boshlash/yakunlash va komissiya hisobi.

Barcha funksiyalar COMMIT QILMAYDI — commit chaqiruvchida.
Buyurtma holati faqat order_flow.transition() orqali o'zgaradi.
"""

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import MasterProfile, MasterService, Order, Payment, Quote, User
from app.models.enums import (
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
    PricingType,
    QuoteStatus,
    Role,
)
from app.services import order_flow

PRICE_ALREADY_CONFIRMED_OR_CHANGED = (
    "Narx allaqachon tasdiqlangan yoki buyurtma holati o'zgargan"
)
PRICE_REQUIRED = "Avval narx tasdiqlanishi kerak"
FORBIDDEN = "Bu amal uchun ruxsat yo'q"


def compute_commission(agreed_price: int, commission_rate: int) -> int:
    """Platforma komissiyasini butun so'mda hisoblaydi (floor bo'lish).

    agreed_price > 0 va 0 <= commission_rate <= 100 bo'lishi shart.
    """
    if (
        isinstance(agreed_price, bool)
        or not isinstance(agreed_price, int)
        or agreed_price <= 0
    ):
        raise ValueError("Kelishilgan narx musbat butun son bo'lishi kerak")
    if (
        isinstance(commission_rate, bool)
        or not isinstance(commission_rate, int)
        or not (0 <= commission_rate <= 100)
    ):
        raise ValueError("Komissiya foizi 0 va 100 oralig'ida bo'lishi kerak")
    return (agreed_price * commission_rate) // 100


def _resolve_master_id(master: MasterProfile | User | None) -> int | None:
    if isinstance(master, MasterProfile):
        return master.id
    if isinstance(master, User) and master.role == Role.MASTER and master.master_profile:
        return master.master_profile.id
    return None


def _require_order_customer(order: Order, actor: User | None) -> None:
    if actor is None or actor.role != Role.CUSTOMER or order.customer_id != actor.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, FORBIDDEN)


def propose_quote(
    db: Session,
    order: Order,
    master: MasterProfile | User,
    price: int,
    note: str | None = None,
) -> Quote:
    """Biriktirilgan usta buyurtma uchun narx taklif qiladi. COMMIT QILMAYDI.

    Avvalgi PROPOSED takliflar rejected qilinadi (bir vaqtda faqat bitta proposed).
    """
    if order.status != OrderStatus.ASSIGNED:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Narx taklifi faqat biriktirilgan buyurtma uchun mumkin",
        )

    master_id = _resolve_master_id(master)
    if master_id is None or order.master_id != master_id:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Bu buyurtma boshqa ustaga biriktirilgan",
        )

    if order.agreed_price is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Buyurtma narxi allaqachon tasdiqlangan",
        )

    if (
        isinstance(price, bool)
        or not isinstance(price, int)
        or price <= 0
        or price > settings.QUOTE_MAX_PRICE
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Narx musbat butun son bo'lishi va maksimal chegaradan oshmasligi kerak",
        )

    # Avvalgi PROPOSED takliflarni rejected qilish
    prev_quotes = db.scalars(
        select(Quote).where(
            Quote.order_id == order.id,
            Quote.status == QuoteStatus.PROPOSED,
        )
    ).all()
    for pq in prev_quotes:
        pq.status = QuoteStatus.REJECTED

    quote = Quote(
        order_id=order.id,
        master_id=master_id,
        price=price,
        note=note,
        status=QuoteStatus.PROPOSED,
    )
    db.add(quote)
    db.flush()
    return quote


def accept_quote(
    db: Session,
    order: Order,
    quote: Quote,
    actor: User,
) -> Order:
    """Mijoz ustaning narx taklifini atomik tarzda tasdiqlaydi. COMMIT QILMAYDI."""
    _require_order_customer(order, actor)

    if quote is None or quote.order_id != order.id:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Narx taklifi bu buyurtmaga tegishli emas",
        )

    if quote.status != QuoteStatus.PROPOSED:
        if order.agreed_price is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                PRICE_ALREADY_CONFIRMED_OR_CHANGED,
            )
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Faqat taklif qilingan narxni tasdiqlash mumkin",
        )

    result = db.execute(
        update(Order)
        .where(
            Order.id == order.id,
            Order.status == OrderStatus.ASSIGNED,
            Order.agreed_price.is_(None),
        )
        .values(agreed_price=quote.price)
    )
    if result.rowcount != 1:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            PRICE_ALREADY_CONFIRMED_OR_CHANGED,
        )

    db.execute(
        update(Quote)
        .where(
            Quote.order_id == order.id,
            Quote.id != quote.id,
            Quote.status == QuoteStatus.PROPOSED,
        )
        .values(status=QuoteStatus.REJECTED)
    )
    db.execute(
        update(Quote)
        .where(Quote.id == quote.id)
        .values(status=QuoteStatus.ACCEPTED)
    )

    db.expire_all()
    db.refresh(order)
    db.refresh(quote)
    return order


def reject_quote(
    db: Session,
    order: Order,
    quote: Quote,
    actor: User,
) -> Quote:
    """Mijoz ustaning narx taklifini rad etadi. COMMIT QILMAYDI."""
    _require_order_customer(order, actor)

    if quote is None or quote.order_id != order.id:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Narx taklifi bu buyurtmaga tegishli emas",
        )

    if quote.status != QuoteStatus.PROPOSED:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Faqat taklif qilingan narxni rad etish mumkin",
        )

    quote.status = QuoteStatus.REJECTED
    db.flush()
    return quote


def apply_fixed_price(db: Session, order: Order) -> Order:
    """Agar biriktirilgan ustaning shu kategoriya bo'yicha xizmati fixed bo'lsa
    va base_price > 0 bo'lsa, order.agreed_price ni atomik tarzda o'rnatadi.
    quote turidagi xizmat uchun hech narsa qilmaydi. COMMIT QILMAYDI.
    """
    if order.master_id is None:
        return order

    service = db.scalar(
        select(MasterService).where(
            MasterService.master_id == order.master_id,
            MasterService.category_id == order.category_id,
        )
    )
    if (
        service is not None
        and service.pricing_type == PricingType.FIXED
        and service.base_price is not None
        and service.base_price > 0
    ):
        result = db.execute(
            update(Order)
            .where(
                Order.id == order.id,
                Order.agreed_price.is_(None),
            )
            .values(agreed_price=service.base_price)
        )
        if result.rowcount:
            db.expire_all()
            db.refresh(order)

    return order


def start_order(db: Session, order: Order, actor: User) -> Order:
    """Ishni boshlash: avval narx tasdiqlangan bo'lishi shart, so'ng assigned -> in_progress.
    COMMIT QILMAYDI.
    """
    from_s = OrderStatus(order.status)
    if not order_flow.can_transition(from_s, OrderStatus.IN_PROGRESS):
        order_flow.transition(db, order, OrderStatus.IN_PROGRESS, actor)
    order_flow._check_actor(order, from_s, OrderStatus.IN_PROGRESS, actor)

    if order.agreed_price is None or order.agreed_price <= 0:
        raise HTTPException(status.HTTP_409_CONFLICT, PRICE_REQUIRED)

    order_flow.transition(db, order, OrderStatus.IN_PROGRESS, actor)
    db.flush()
    return order


def complete_order(db: Session, order: Order, actor: User) -> Order:
    """Ishni yakunlash: in_progress -> completed, komissiya hisoblash va naqd to'lov yaratish.
    COMMIT QILMAYDI.
    """
    from_s = OrderStatus(order.status)
    if not order_flow.can_transition(from_s, OrderStatus.COMPLETED):
        order_flow.transition(db, order, OrderStatus.COMPLETED, actor)
    order_flow._check_actor(order, from_s, OrderStatus.COMPLETED, actor)

    if order.agreed_price is None or order.agreed_price <= 0:
        raise HTTPException(status.HTTP_409_CONFLICT, PRICE_REQUIRED)

    order_flow.transition(db, order, OrderStatus.COMPLETED, actor)
    order.commission_amount = compute_commission(
        order.agreed_price, order.commission_rate
    )
    payment = Payment(
        order_id=order.id,
        method=PaymentMethod.CASH,
        amount=order.agreed_price,
        status=PaymentStatus.PAID,
    )
    db.add(payment)
    db.flush()
    return order
