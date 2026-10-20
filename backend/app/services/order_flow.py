"""Buyurtma holatlari: kodda order.status FAQAT shu modulda o'zgaradi.

Ishlatish (endpointda):
    transition(db, order, OrderStatus.CANCELLED, actor=current_user)
    db.commit()   # commit chaqiruvchida

Ikki bosqichli tekshiruv:
  1. Holatlar jadvali (TRANSITIONS): umuman bunday o'tish bormi? Yo'q -> 409.
  2. Aktor qoidalari (_check_actor): shu foydalanuvchi buni qila oladimi? Yo'q -> 403.
"""

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import Order, OrderStatusHistory, User
from app.models.enums import OrderStatus, Role

S = OrderStatus

ILLEGAL_TRANSITION = "Bu holatdan o'tish mumkin emas"
FORBIDDEN = "Bu amal uchun ruxsat yo'q"

# Ruxsat etilgan o'tishlar. completed va cancelled: yakuniy (bo'sh to'plam).
TRANSITIONS: dict[OrderStatus, frozenset[OrderStatus]] = {
    S.SEARCHING: frozenset({S.ASSIGNED, S.CANCELLED}),
    S.ASSIGNED: frozenset({S.IN_PROGRESS, S.CANCELLED, S.SEARCHING}),
    S.IN_PROGRESS: frozenset({S.COMPLETED, S.CANCELLED}),
    S.COMPLETED: frozenset(),
    S.CANCELLED: frozenset(),
}

TERMINAL: frozenset[OrderStatus] = frozenset(s for s, nxt in TRANSITIONS.items() if not nxt)

# Mijoz faqat o'z buyurtmasini va faqat shu holatlardan bekor qila oladi
CUSTOMER_CANCELLABLE: frozenset[OrderStatus] = frozenset({S.SEARCHING, S.ASSIGNED})

# Usta o'tishlari (keyingi kunlarda endpointlar chaqiradi). Usta faqat o'ziga
# biriktirilgan buyurtmada ishlaydi: order.master_id == usta profili id.
# searching -> assigned uchun chaqiruvchi avval order.master_id ni o'rnatadi.
MASTER_TRANSITIONS: frozenset[tuple[OrderStatus, OrderStatus]] = frozenset({
    (S.SEARCHING, S.ASSIGNED),    # taklifni qabul qilish
    (S.ASSIGNED, S.SEARCHING),    # voz kechish -> qayta qidiruv
    (S.ASSIGNED, S.IN_PROGRESS),  # ishni boshlash
    (S.IN_PROGRESS, S.COMPLETED), # ishni yakunlash
})

# Admin: istalgan yakuniy bo'lmagan buyurtmani bekor qiladi, ustani
# biriktiradi yoki biriktirishni bekor qiladi. Ishni boshlash/yakunlash ustaning ishi.
ADMIN_TRANSITIONS: frozenset[tuple[OrderStatus, OrderStatus]] = frozenset({
    (S.SEARCHING, S.CANCELLED),
    (S.ASSIGNED, S.CANCELLED),
    (S.IN_PROGRESS, S.CANCELLED),
    (S.SEARCHING, S.ASSIGNED),
    (S.ASSIGNED, S.SEARCHING),
})


def can_transition(from_status: OrderStatus, to_status: OrderStatus) -> bool:
    """Faqat jadval tekshiruvi (aktorsiz). UI tugmalarini ko'rsatish uchun ham qulay."""
    return OrderStatus(to_status) in TRANSITIONS.get(OrderStatus(from_status), frozenset())


def _forbidden() -> HTTPException:
    return HTTPException(status.HTTP_403_FORBIDDEN, FORBIDDEN)


def _master_profile_id(actor: User) -> int | None:
    profile = actor.master_profile
    return profile.id if profile is not None else None


def _check_actor(order: Order, from_s: OrderStatus, to_s: OrderStatus, actor: User) -> None:
    pair = (from_s, to_s)

    if actor.role == Role.CUSTOMER:
        if order.customer_id != actor.id:
            raise _forbidden()
        if to_s == S.CANCELLED and from_s in CUSTOMER_CANCELLABLE:
            return
        raise _forbidden()

    if actor.role == Role.MASTER:
        pid = _master_profile_id(actor)
        if pair in MASTER_TRANSITIONS and pid is not None and order.master_id == pid:
            return
        raise _forbidden()

    if actor.role == Role.ADMIN:
        if pair in ADMIN_TRANSITIONS:
            return
        raise _forbidden()

    raise _forbidden()


def transition(db: Session, order: Order, to_status: OrderStatus | str, actor: User) -> OrderStatusHistory:
    """Holatni tekshirib o'zgartiradi va tarixga yozadi. COMMIT QILMAYDI.

    409: jadvalda bunday o'tish yo'q (yakuniy holat, bir xil holat ham shu yerda).
    403: aktorga ruxsat yo'q (rol yoki egalik).
    """
    try:
        to_s = OrderStatus(to_status)
    except ValueError:
        raise HTTPException(status.HTTP_409_CONFLICT, ILLEGAL_TRANSITION)
    from_s = OrderStatus(order.status)

    if not can_transition(from_s, to_s):
        raise HTTPException(status.HTTP_409_CONFLICT, ILLEGAL_TRANSITION)
    _check_actor(order, from_s, to_s, actor)

    order.status = to_s
    entry = OrderStatusHistory(
        order=order, from_status=from_s, to_status=to_s, changed_by=actor.id
    )
    db.add(entry)
    return entry


def create_order_history(db: Session, order: Order, actor: User) -> OrderStatusHistory:
    """Yangi buyurtma uchun birinchi yozuv: None -> searching. COMMIT QILMAYDI."""
    order.status = S.SEARCHING
    entry = OrderStatusHistory(
        order=order, from_status=None, to_status=S.SEARCHING, changed_by=actor.id
    )
    db.add(entry)
    return entry
