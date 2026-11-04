from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Path, Query, UploadFile, status
from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user, require_role
from app.core.config import MAX_DB_INT
from app.db.session import get_db
from app.models import Category, ChatReport, Dispute, MasterProfile, MasterService, Order, OrderMessage, OrderOffer, OrderPhoto, OrderStatusHistory, Quote, Review, User
from app.models.enums import DisputeStatus, OfferStatus, OrderStatus, Role, SelectionMode
from app.schemas.dispute import DisputeCreate, DisputeOut, UserDisputeListItem
from app.schemas.message import MessageIn, MessageOut
from app.schemas.order import (
    OfferOut,
    OrderCompleteOut,
    OrderCreate,
    OrderDetailOut,
    OrderListItem,
    OrderOut,
    SelectMasterIn,
)
from app.schemas.photo import PhotoOut
from app.schemas.quote import QuoteIn, QuoteOut
from app.schemas.review import OrderReviewOut, ReviewCreate, ReviewOut
from app.schemas.mobile import ChatReportIn, ChatReportOut, DispatchStatusOut
from app.services import matching, notify, pricing, reviews, storage
from app.services.order_flow import assign_master, create_order_history, transition

router = APIRouter(prefix="/orders", tags=["orders"])

MAX_ORDER_PHOTOS = 5

_ORDER_OPTS = (
    selectinload(Order.history),
    selectinload(Order.category),
    selectinload(Order.offers),
    selectinload(Order.quotes),
    selectinload(Order.master).selectinload(MasterProfile.user),
    selectinload(Order.photos),
)


def _is_expired(expires_at: datetime | None) -> bool:
    if expires_at is None:
        return False
    now = datetime.now(timezone.utc)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at < now


def _own_order(order_id: int, user: User, db: Session) -> Order:
    """Foydalanuvchining O'Z buyurtmasini qaytaradi; yo'q yoki begona -> 404."""
    order = db.scalar(
        select(Order)
        .where(Order.id == order_id, Order.customer_id == user.id)
        .options(*_ORDER_OPTS)
    )
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Buyurtma topilmadi")
    return order


def _offer_out(offer: OrderOffer, db: Session) -> OfferOut:
    """OrderOffer -> OfferOut (master_name bilan)."""
    master = db.get(MasterProfile, offer.master_id)
    master_name = ""
    if master:
        user = db.get(User, master.user_id)
        master_name = user.full_name if user else ""
    return OfferOut(
        id=offer.id,
        master_id=offer.master_id,
        master_name=master_name,
        master_full_name=master_name,
        status=offer.status.value if hasattr(offer.status, "value") else str(offer.status),
        expires_at=offer.expires_at,
    )


def _order_out(order: Order, db: Session, note: str | None = None) -> OrderOut:
    master_name = None
    if order.master and order.master.user:
        master_name = order.master.user.full_name
    elif order.master_id:
        mp = db.get(MasterProfile, order.master_id)
        if mp:
            u = db.get(User, mp.user_id)
            master_name = u.full_name if u else None

    offers = [_offer_out(o, db) for o in (order.offers or [])]
    return OrderOut(
        id=order.id,
        customer_id=order.customer_id,
        category_id=order.category_id,
        category_name=order.category.name,
        master_id=order.master_id,
        master_name=master_name,
        master_full_name=master_name,
        description=order.description,
        city=order.city,
        district=order.district,
        address=order.address,
        latitude=order.latitude,
        longitude=order.longitude,
        status=order.status,
        selection_mode=order.selection_mode,
        agreed_price=order.agreed_price,
        commission_rate=order.commission_rate,
        created_at=order.created_at,
        history=order.history,
        offers=offers,
        note=note,
    )


def _order_detail_out(order: Order, db: Session, note: str | None = None) -> OrderDetailOut:
    master_name = None
    if order.master and order.master.user:
        master_name = order.master.user.full_name
    elif order.master_id:
        mp = db.get(MasterProfile, order.master_id)
        if mp:
            u = db.get(User, mp.user_id)
            master_name = u.full_name if u else None

    offers = [_offer_out(o, db) for o in (order.offers or [])]
    quotes = [
        QuoteOut.model_validate(q)
        for q in sorted(order.quotes or [], key=lambda x: x.id)
    ]
    final_price = order.agreed_price if order.status == OrderStatus.COMPLETED else None

    rev = db.scalar(select(Review).where(Review.order_id == order.id))
    review_out = OrderReviewOut.model_validate(rev) if rev else None
    can_review = bool(order.status == OrderStatus.COMPLETED and rev is None)

    photos = [storage.url_for(p.file_path) for p in (order.photos or [])]

    return OrderDetailOut(
        id=order.id,
        customer_id=order.customer_id,
        category_id=order.category_id,
        category_name=order.category.name,
        master_id=order.master_id,
        master_name=master_name,
        master_full_name=master_name,
        description=order.description,
        city=order.city,
        district=order.district,
        address=order.address,
        latitude=order.latitude,
        longitude=order.longitude,
        status=order.status,
        selection_mode=order.selection_mode,
        agreed_price=order.agreed_price,
        final_price=final_price,
        commission_rate=order.commission_rate,
        quotes=quotes,
        created_at=order.created_at,
        history=order.history,
        offers=offers,
        review=review_out,
        can_review=can_review,
        note=note,
        photos=photos,
    )


def _list_item(order: Order, db: Session) -> OrderListItem:
    master_name = None
    if order.master_id:
        mp = db.get(MasterProfile, order.master_id)
        if mp:
            u = db.get(User, mp.user_id)
            master_name = u.full_name if u else None
    offers = [_offer_out(o, db) for o in (order.offers or [])]
    quotes = [
        QuoteOut.model_validate(q)
        for q in sorted(order.quotes or [], key=lambda x: x.id)
    ]
    return OrderListItem(
        id=order.id,
        category_id=order.category_id,
        category_name=order.category.name,
        description=order.description,
        city=order.city,
        district=order.district,
        latitude=order.latitude,
        longitude=order.longitude,
        status=order.status,
        selection_mode=order.selection_mode,
        agreed_price=order.agreed_price,
        master_id=order.master_id,
        master_name=master_name,
        master_full_name=master_name,
        created_at=order.created_at,
        offers=offers,
        quotes=quotes,
    )


# ==================== ENDPOINTS ====================


@router.post("", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
def create_order(
    data: OrderCreate,
    user: User = Depends(require_role(Role.CUSTOMER)),
    db: Session = Depends(get_db),
):
    cat = db.get(Category, data.category_id)
    if cat is None or not cat.is_active:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Kategoriya topilmadi yoki faol emas",
        )

    order = Order(
        customer_id=user.id,
        category_id=data.category_id,
        description=data.description,
        city=data.city,
        district=data.district,
        address=data.address,
        latitude=data.latitude,
        longitude=data.longitude,
        selection_mode=SelectionMode(data.selection_mode),
        master_id=None,
        agreed_price=None,
        commission_rate=pricing.current_commission_rate(db),
        commission_amount=None,
    )
    db.add(order)
    db.flush()
    create_order_history(db, order, user)

    note = None
    if order.selection_mode == SelectionMode.AUTOMATIC:
        offers, dispatch_state = matching.dispatch_next_wave(db, order)
        if not offers and dispatch_state == "exhausted":
            note = "Mos usta topilmadi"

    db.commit()
    return _order_out(_own_order(order.id, user, db), db, note=note)


def _dispatch_status(order: Order, db: Session) -> DispatchStatusOut:
    counts = dict(
        db.execute(
            select(OrderOffer.status, func.count(OrderOffer.id))
            .where(OrderOffer.order_id == order.id)
            .group_by(OrderOffer.status)
        ).all()
    )
    pending = counts.get(OfferStatus.PENDING, 0)
    rejected = counts.get(OfferStatus.REJECTED, 0)
    expired = counts.get(OfferStatus.EXPIRED, 0)
    if order.status == OrderStatus.ASSIGNED:
        state, message = "assigned", "Usta buyurtmani qabul qildi"
    elif order.status != OrderStatus.SEARCHING:
        state, message = order.status.value, "Buyurtma qidiruvda emas"
    elif pending:
        state, message = "waiting", "Ustalar javobi kutilmoqda"
    elif order.dispatch_radius_km >= 999:
        state, message = "exhausted", "Mos ustalar topilmadi"
    else:
        state, message = "searching", "Usta qidiruvi davom etmoqda"
    return DispatchStatusOut(
        order_id=order.id, status=state,
        dispatch_radius_km=order.dispatch_radius_km,
        pending_offers=pending, rejected_offers=rejected,
        expired_offers=expired, accepted_master_id=order.master_id,
        message=message,
    )


@router.post("/{order_id}/dispatch", response_model=DispatchStatusOut)
def dispatch_order(
    order_id: int = Path(..., le=MAX_DB_INT),
    user: User = Depends(require_role(Role.CUSTOMER)),
    db: Session = Depends(get_db),
):
    order = _own_order(order_id, user, db)
    if order.selection_mode != SelectionMode.AUTOMATIC:
        raise HTTPException(status.HTTP_409_CONFLICT, "Dispatch faqat automatic buyurtma uchun")
    offers, _ = matching.dispatch_next_wave(db, order)
    db.commit()
    db.refresh(order)
    result = _dispatch_status(order, db)
    if not offers and result.status == "searching":
        result.message = "Bu radiusda usta topilmadi; qayta dispatch qilib radiusni kengaytiring"
    return result


@router.get("/{order_id}/dispatch-status", response_model=DispatchStatusOut)
def get_dispatch_status(
    order_id: int = Path(..., le=MAX_DB_INT),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Buyurtma topilmadi")
    if user.role == Role.CUSTOMER and order.customer_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Buyurtma topilmadi")
    if user.role == Role.MASTER:
        profile = db.scalar(select(MasterProfile).where(MasterProfile.user_id == user.id))
        has_offer = (
            db.scalar(select(OrderOffer.id).where(
                OrderOffer.order_id == order.id, OrderOffer.master_id == profile.id
            ))
            if profile is not None
            else None
        )
        if profile is None or (has_offer is None and order.master_id != profile.id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Buyurtma topilmadi")
    if user.role not in {Role.CUSTOMER, Role.MASTER, Role.ADMIN}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Ruxsat yo'q")
    matching.expire_stale_offers(db, order)
    db.commit()
    db.refresh(order)
    return _dispatch_status(order, db)


@router.get("", response_model=list[OrderListItem])
def list_orders(
    status_filter: OrderStatus | None = None,
    limit: int = 20,
    offset: int = Query(default=0, le=MAX_DB_INT),
    user: User = Depends(require_role(Role.CUSTOMER)),
    db: Session = Depends(get_db),
):
    matching.rotate_stale_automatic_orders(db, customer_id=user.id)
    db.commit()

    limit = min(max(limit, 1), 100)
    offset = min(max(offset, 0), MAX_DB_INT)

    stmt = (
        select(Order)
        .where(Order.customer_id == user.id)
        .options(
            selectinload(Order.category),
            selectinload(Order.offers),
            selectinload(Order.quotes),
        )
        .order_by(Order.id.desc())
        .limit(limit)
        .offset(offset)
    )
    if status_filter is not None:
        stmt = stmt.where(Order.status == status_filter)

    orders = db.scalars(stmt).all()
    return [_list_item(o, db) for o in orders]


def _notify_admins_of_dispute(
    db: Session, user: User, dispute: Dispute, order: Order | None = None
) -> None:
    role_label = "Mijoz" if user.role == Role.CUSTOMER else "Usta"
    order_part = f"Buyurtma #{order.id} bo'yicha " if order else ""
    title = f"Yangi shikoyat ({role_label})"
    body = f"{order_part}{role_label} {user.full_name} ({user.phone}) shikoyat yubordi: {dispute.reason[:120]}"
    admins = db.scalars(
        select(User).where(User.role == Role.ADMIN, User.is_active.is_(True))
    ).all()
    for adm in admins:
        notify.notify_user(
            db,
            adm.id,
            "new_dispute",
            title,
            body,
            order_id=order.id if order else None,
        )


@router.get("/my-disputes", response_model=list[UserDisputeListItem])
def list_my_disputes(
    status_filter: DisputeStatus | None = Query(default=None, alias="status"),
    user: User = Depends(require_role(Role.CUSTOMER, Role.MASTER)),
    db: Session = Depends(get_db),
):
    stmt = (
        select(Dispute, Order.status, Category.name)
        .outerjoin(Order, Dispute.order_id == Order.id)
        .outerjoin(Category, Order.category_id == Category.id)
        .where(Dispute.raised_by == user.id)
        .order_by(Dispute.created_at.desc(), Dispute.id.desc())
    )
    if status_filter is not None:
        stmt = stmt.where(Dispute.status == status_filter)
    rows = db.execute(stmt).all()
    return [
        UserDisputeListItem(
            id=d.id,
            order_id=d.order_id,
            category_name=cat_name or "Umumiy shikoyat",
            order_status=(
                order_status.value
                if hasattr(order_status, "value")
                else (str(order_status) if order_status else None)
            ),
            status=d.status,
            reason=d.reason,
            admin_note=d.admin_note,
            created_at=d.created_at,
            resolved_at=d.resolved_at,
        )
        for d, order_status, cat_name in rows
    ]


@router.post(
    "/my-disputes", response_model=DisputeOut, status_code=status.HTTP_201_CREATED
)
def create_my_dispute(
    data: DisputeCreate,
    user: User = Depends(require_role(Role.CUSTOMER, Role.MASTER)),
    db: Session = Depends(get_db),
):
    order: Order | None = None
    if data.order_id is not None:
        order = db.get(Order, data.order_id)
        if order is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Buyurtma topilmadi")
        if user.role == Role.CUSTOMER:
            if order.customer_id != user.id:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Buyurtma topilmadi")
        elif user.role == Role.MASTER:
            profile = db.scalar(
                select(MasterProfile).where(MasterProfile.user_id == user.id)
            )
            has_offer = (
                db.scalar(
                    select(OrderOffer.id).where(
                        OrderOffer.order_id == order.id,
                        OrderOffer.master_id == profile.id,
                    )
                )
                if profile
                else None
            )
            if profile is None or (order.master_id != profile.id and has_offer is None):
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Buyurtma topilmadi")

        if order.status not in _DISPUTE_ALLOWED_STATUSES:
            raise HTTPException(status.HTTP_409_CONFLICT, DISPUTE_WRONG_STATUS)

        existing_open = db.scalar(
            select(Dispute).where(
                Dispute.order_id == order.id, Dispute.status == DisputeStatus.OPEN
            )
        )
        if existing_open is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, DISPUTE_ALREADY_OPEN)

    dispute = Dispute(
        order_id=order.id if order else None,
        raised_by=user.id,
        reason=data.reason,
    )
    db.add(dispute)
    db.flush()
    _notify_admins_of_dispute(db, user, dispute, order)
    db.commit()
    db.refresh(dispute)
    return dispute


@router.get("/{order_id}", response_model=OrderDetailOut)
def get_order(
    order_id: int = Path(..., le=MAX_DB_INT),
    user: User = Depends(require_role(Role.CUSTOMER)),
    db: Session = Depends(get_db),
):
    order = _own_order(order_id, user, db)
    matching.rotate_stale_automatic_orders(db, order)
    db.commit()
    db.expire_all()
    return _order_detail_out(_own_order(order_id, user, db), db)


@router.post("/{order_id}/cancel", response_model=OrderOut)
def cancel_order(
    order_id: int = Path(..., le=MAX_DB_INT),
    user: User = Depends(require_role(Role.CUSTOMER)),
    db: Session = Depends(get_db),
):
    order = _own_order(order_id, user, db)
    master_user_id = order.master.user_id if order.master is not None else None
    transition(db, order, OrderStatus.CANCELLED, user)
    if master_user_id is not None:
        notify.notify_user(
            db, master_user_id, "order_cancelled", "Buyurtma bekor qilindi",
            f"#{order.id} buyurtma mijoz tomonidan bekor qilindi", order_id=order.id,
        )
    db.commit()
    return _order_out(_own_order(order.id, user, db), db)


# ---------- Manual usta tanlash ----------


@router.post("/{order_id}/select-master")
def select_master(
    data: SelectMasterIn,
    order_id: int = Path(..., le=MAX_DB_INT),
    user: User = Depends(require_role(Role.CUSTOMER)),
    db: Session = Depends(get_db),
):
    order = _own_order(order_id, user, db)
    # Muddati o'tgan takliflarni belgilash (faqat shu buyurtma uchun)
    if matching.expire_stale_offers(db, order):
        db.commit()
        order = _own_order(order_id, user, db)

    if order.selection_mode != SelectionMode.MANUAL:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Bu buyurtma uchun usta tanlash faqat qo'lda (manual) rejimda mumkin",
        )
    if order.status != OrderStatus.SEARCHING:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Buyurtma hozir qidiruv holatida emas",
        )

    # Pending taklif borligini tekshirish
    if any(o.status == OfferStatus.PENDING for o in order.offers):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Avvalgi taklifga javob kutilmoqda",
        )

    # Usta mavjud va mos ekanligini tekshirish
    master = db.get(MasterProfile, data.master_id)
    if master is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Usta topilmadi",
        )
    master_user = db.get(User, master.user_id)
    if not master.is_approved:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Usta tasdiqlanmagan",
        )
    if not master.is_available:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Usta hozirda mavjud emas yoki band",
        )
    if not master_user or not master_user.is_active:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Usta foydalanuvchisi faol emas",
        )
    if master.city.strip().lower() != order.city.strip().lower():
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Usta boshqa shaharda joylashgan",
        )

    has_service = db.scalar(
        select(
            exists().where(
                MasterService.master_id == master.id,
                MasterService.category_id == order.category_id,
            )
        )
    )
    if not has_service:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Usta bu turdagi xizmatni ko'rsatmaydi",
        )

    existing_offer = db.scalar(
        select(OrderOffer).where(
            OrderOffer.order_id == order.id,
            OrderOffer.master_id == master.id,
        )
    )
    if existing_offer is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Bu ustaga allaqachon taklif yuborilgan",
        )

    offer = matching.create_offer(db, order, master)
    db.commit()
    db.refresh(offer)
    return {"detail": "Taklif yuborildi", "offer_id": offer.id}


# ---------- Usta qabul / rad ----------


@router.post("/{order_id}/accept")
def accept_offer(
    order_id: int = Path(..., le=MAX_DB_INT),
    user: User = Depends(require_role(Role.MASTER)),
    db: Session = Depends(get_db),
):
    profile = db.scalar(
        select(MasterProfile).where(MasterProfile.user_id == user.id)
    )
    if profile is None or not profile.is_approved:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Tasdiqlangan usta profili topilmadi")

    offer = db.scalar(
        select(OrderOffer).where(
            OrderOffer.order_id == order_id,
            OrderOffer.master_id == profile.id,
        )
    )
    if offer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Taklif topilmadi")

    if offer.status == OfferStatus.EXPIRED or (
        offer.status == OfferStatus.PENDING and _is_expired(offer.expires_at)
    ):
        if offer.status == OfferStatus.PENDING:
            offer.status = OfferStatus.EXPIRED
            db.commit()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Taklif muddati tugagan",
        )

    if offer.status != OfferStatus.PENDING:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Taklif muddati tugagan yoki bekor qilingan",
        )

    order = assign_master(db, order_id, profile.id, user)
    order = pricing.apply_fixed_price(db, order)
    db.commit()
    return {"detail": "Buyurtma qabul qilindi", "order_id": order.id}


@router.post("/{order_id}/reject")
def reject_offer(
    order_id: int = Path(..., le=MAX_DB_INT),
    user: User = Depends(require_role(Role.MASTER)),
    db: Session = Depends(get_db),
):
    profile = db.scalar(
        select(MasterProfile).where(MasterProfile.user_id == user.id)
    )
    if profile is None or not profile.is_approved:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Tasdiqlangan usta profili topilmadi")

    offer = db.scalar(
        select(OrderOffer).where(
            OrderOffer.order_id == order_id,
            OrderOffer.master_id == profile.id,
            OrderOffer.status == OfferStatus.PENDING,
        )
    )
    if offer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Taklif topilmadi")

    offer.status = OfferStatus.REJECTED

    order = db.get(Order, order_id)
    next_offered = False
    if (
        order
        and order.selection_mode == SelectionMode.AUTOMATIC
        and order.status == OrderStatus.SEARCHING
    ):
        new_offers, _ = matching.dispatch_next_wave(db, order)
        next_offered = len(new_offers) > 0
        notify.notify_user(
            db, order.customer_id, "offer_rejected", "Usta taklifni rad etdi",
            f"#{order.id} buyurtmasi uchun boshqa usta qidirilmoqda", order_id=order.id,
        )

    db.commit()
    return {
        "detail": "Taklif rad etildi",
        "next_master_offered": next_offered,
    }


# ---------- Narx takliflari (Quotes) ----------


@router.post(
    "/{order_id}/quotes",
    response_model=QuoteOut,
    status_code=status.HTTP_201_CREATED,
)
def propose_quote(
    data: QuoteIn,
    order_id: int = Path(..., le=MAX_DB_INT),
    user: User = Depends(require_role(Role.MASTER)),
    db: Session = Depends(get_db),
):
    profile = db.scalar(
        select(MasterProfile).where(MasterProfile.user_id == user.id)
    )
    if profile is None or not profile.is_approved:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Tasdiqlangan usta profili topilmadi")

    order = db.get(Order, order_id)
    if order is None or order.master_id != profile.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Buyurtma topilmadi")

    quote = pricing.propose_quote(
        db, order, profile, price=data.price, note=data.note
    )
    db.commit()
    db.refresh(quote)
    return quote


@router.post("/{order_id}/quotes/{quote_id}/accept")
def accept_quote(
    order_id: int = Path(..., le=MAX_DB_INT),
    quote_id: int = Path(..., le=MAX_DB_INT),
    user: User = Depends(require_role(Role.CUSTOMER)),
    db: Session = Depends(get_db),
):
    order = db.get(Order, order_id)
    if order is None or order.customer_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Buyurtma topilmadi")

    quote = db.get(Quote, quote_id)
    if quote is None or quote.order_id != order.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Narx taklifi topilmadi")

    try:
        order = pricing.accept_quote(db, order, quote, user)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {
        "detail": "Narx taklifi qabul qilindi",
        "order_id": order.id,
        "agreed_price": order.agreed_price,
    }


@router.post("/{order_id}/quotes/{quote_id}/reject")
def reject_quote(
    order_id: int = Path(..., le=MAX_DB_INT),
    quote_id: int = Path(..., le=MAX_DB_INT),
    user: User = Depends(require_role(Role.CUSTOMER)),
    db: Session = Depends(get_db),
):
    order = db.get(Order, order_id)
    if order is None or order.customer_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Buyurtma topilmadi")

    quote = db.get(Quote, quote_id)
    if quote is None or quote.order_id != order.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Narx taklifi topilmadi")

    pricing.reject_quote(db, order, quote, user)
    db.commit()
    return {
        "detail": "Narx taklifi rad etildi",
        "quote_id": quote.id,
    }


# ---------- Ishni boshlash va yakunlash ----------


@router.post("/{order_id}/start")
def start_order(
    order_id: int = Path(..., le=MAX_DB_INT),
    user: User = Depends(require_role(Role.MASTER)),
    db: Session = Depends(get_db),
):
    profile = db.scalar(
        select(MasterProfile).where(MasterProfile.user_id == user.id)
    )
    if profile is None or not profile.is_approved:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Tasdiqlangan usta profili topilmadi")

    order = db.get(Order, order_id)
    if order is None or order.master_id != profile.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Buyurtma topilmadi")

    order = pricing.start_order(db, order, user)
    db.commit()
    return {
        "detail": "Ish boshlandi",
        "order_id": order.id,
        "status": order.status,
    }


@router.post("/{order_id}/complete", response_model=OrderCompleteOut)
def complete_order(
    order_id: int = Path(..., le=MAX_DB_INT),
    user: User = Depends(require_role(Role.MASTER)),
    db: Session = Depends(get_db),
):
    profile = db.scalar(
        select(MasterProfile).where(MasterProfile.user_id == user.id)
    )
    if profile is None or not profile.is_approved:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Tasdiqlangan usta profili topilmadi")

    order = db.get(Order, order_id)
    if order is None or order.master_id != profile.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Buyurtma topilmadi")

    order = pricing.complete_order(db, order, user)
    db.commit()
    net = order.agreed_price - order.commission_amount
    return OrderCompleteOut(
        order_id=order.id,
        status=order.status,
        price=order.agreed_price,
        commission_rate=order.commission_rate,
        commission_amount=order.commission_amount,
        net_amount=net,
        net=net,
        detail="Ish muvaffaqiyatli yakunlandi",
    )


@router.post("/{order_id}/review", response_model=ReviewOut, status_code=status.HTTP_201_CREATED)
def submit_order_review(
    data: ReviewCreate,
    order_id: int = Path(..., le=MAX_DB_INT),
    user: User = Depends(require_role(Role.CUSTOMER)),
    db: Session = Depends(get_db),
):
    order = _own_order(order_id, user, db)
    rev = reviews.create_review(
        db=db,
        order=order,
        customer=user,
        rating=data.rating,
        comment=data.comment,
        quality_rating=data.quality_rating,
        timeliness_rating=data.timeliness_rating,
        price_rating=data.price_rating,
    )
    db.commit()
    db.refresh(rev)
    return rev


# ---------- Rasmlar ----------


@router.post(
    "/{order_id}/photos",
    response_model=list[PhotoOut],
    status_code=status.HTTP_201_CREATED,
)
async def upload_order_photos(
    order_id: int = Path(..., le=MAX_DB_INT),
    files: list[UploadFile] = File(...),
    user: User = Depends(require_role(Role.CUSTOMER)),
    db: Session = Depends(get_db),
):
    order = _own_order(order_id, user, db)

    existing = db.scalar(
        select(func.count(OrderPhoto.id)).where(OrderPhoto.order_id == order.id)
    )
    if (existing or 0) + len(files) > MAX_ORDER_PHOTOS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Buyurtmaga ko'pi bilan {MAX_ORDER_PHOTOS} ta rasm yuklash mumkin",
        )

    saved: list[OrderPhoto] = []
    for f in files:
        rel_path = await storage.save_image(f, "order_photos")
        photo = OrderPhoto(order_id=order.id, file_path=rel_path)
        db.add(photo)
        saved.append(photo)
    db.commit()
    for p in saved:
        db.refresh(p)

    return [
        PhotoOut(id=p.id, url=storage.url_for(p.file_path), created_at=p.created_at)
        for p in saved
    ]


@router.delete("/{order_id}/photos/{photo_id}")
def delete_order_photo(
    order_id: int = Path(..., le=MAX_DB_INT),
    photo_id: int = Path(..., le=MAX_DB_INT),
    user: User = Depends(require_role(Role.CUSTOMER)),
    db: Session = Depends(get_db),
):
    order = _own_order(order_id, user, db)
    photo = db.get(OrderPhoto, photo_id)
    if photo is None or photo.order_id != order.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rasm topilmadi")

    storage.delete_image(photo.file_path)
    db.delete(photo)
    db.commit()
    return {"detail": "Rasm o'chirildi"}


# ---------- Umumiy: buyurtma ishtirokchisi tekshiruvi (chat va shikoyat) ----------

PARTICIPANT_NOT_FOUND = "Buyurtma topilmadi"
PARTICIPANT_FORBIDDEN = "Bu amal uchun ruxsat yo'q"


def _order_for_participant(order_id: int, user: User, db: Session) -> tuple[Order, bool]:
    """Qaytaradi: (order, can_write). Mijoz/biriktirilgan usta o'qiy/yoza oladi,
    admin faqat o'qiy oladi. Ruxsat yo'q yoki topilmasa -> 404."""
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, PARTICIPANT_NOT_FOUND)

    if user.role == Role.CUSTOMER:
        if order.customer_id != user.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, PARTICIPANT_NOT_FOUND)
        return order, True

    if user.role == Role.MASTER:
        profile = db.scalar(select(MasterProfile).where(MasterProfile.user_id == user.id))
        if profile is None or order.master_id != profile.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, PARTICIPANT_NOT_FOUND)
        return order, True

    if user.role == Role.ADMIN:
        return order, False

    raise HTTPException(status.HTTP_403_FORBIDDEN, PARTICIPANT_FORBIDDEN)


# ---------- Chat ----------

CHAT_NOT_OPEN = "Chat faqat usta biriktirilgandan keyin ochiladi"


@router.get("/{order_id}/messages", response_model=list[MessageOut])
def list_order_messages(
    order_id: int = Path(..., le=MAX_DB_INT),
    limit: int = 50,
    offset: int = Query(default=0, le=MAX_DB_INT),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order, _ = _order_for_participant(order_id, user, db)

    limit = min(max(limit, 1), 200)
    offset = min(max(offset, 0), MAX_DB_INT)

    stmt = select(OrderMessage, User.full_name).join(User, OrderMessage.sender_id == User.id).where(
        OrderMessage.order_id == order.id
    )
    if user.role != Role.ADMIN:
        stmt = stmt.where(OrderMessage.is_hidden.is_(False))
    rows = db.execute(
        stmt.order_by(OrderMessage.id.asc())
        .offset(offset)
        .limit(limit)
    ).all()

    return [
        MessageOut(
            id=m.id,
            order_id=m.order_id,
            sender_id=m.sender_id,
            sender_name=name,
            body=m.body,
            created_at=m.created_at,
        )
        for m, name in rows
    ]


@router.post(
    "/{order_id}/messages", response_model=MessageOut, status_code=status.HTTP_201_CREATED
)
def create_order_message(
    data: MessageIn,
    order_id: int = Path(..., le=MAX_DB_INT),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order, can_write = _order_for_participant(order_id, user, db)
    if not can_write:
        raise HTTPException(status.HTTP_403_FORBIDDEN, PARTICIPANT_FORBIDDEN)
    if order.master_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT, CHAT_NOT_OPEN)

    msg = OrderMessage(order_id=order.id, sender_id=user.id, body=data.body)
    db.add(msg)
    if user.role == Role.MASTER:
        recipient_id: int | None = order.customer_id
    else:
        recipient_id = db.scalar(
            select(MasterProfile.user_id).where(MasterProfile.id == order.master_id)
        )
    if recipient_id is not None:
        notify.notify_user(db, recipient_id, "new_message", "Yangi xabar",
                           f"#{order.id} buyurtmasida yangi xabar bor", order_id=order.id)
    db.commit()
    db.refresh(msg)

    return MessageOut(
        id=msg.id,
        order_id=msg.order_id,
        sender_id=msg.sender_id,
        sender_name=user.full_name,
        body=msg.body,
        created_at=msg.created_at,
    )


@router.post("/{order_id}/messages/{message_id}/report", response_model=ChatReportOut,
             status_code=status.HTTP_201_CREATED)
def report_chat_message(
    data: ChatReportIn,
    order_id: int = Path(..., le=MAX_DB_INT),
    message_id: int = Path(..., le=MAX_DB_INT),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order, can_write = _order_for_participant(order_id, user, db)
    if not can_write:
        raise HTTPException(status.HTTP_403_FORBIDDEN, PARTICIPANT_FORBIDDEN)
    message = db.scalar(select(OrderMessage).where(
        OrderMessage.id == message_id, OrderMessage.order_id == order.id
    ))
    if message is None or message.sender_id == user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Shikoyat qilinadigan xabar topilmadi")
    report = ChatReport(order_id=order.id, message_id=message.id,
                        reported_by=user.id, reason=data.reason)
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


# ---------- Shikoyat/nizo ----------

DISPUTE_WRONG_STATUS = (
    "Shikoyat faqat biriktirilgan, jarayondagi, yakunlangan yoki bekor qilingan buyurtma uchun mumkin"
)
DISPUTE_ALREADY_OPEN = "Bu buyurtma bo'yicha allaqachon ko'rib chiqilayotgan shikoyat bor"
_DISPUTE_ALLOWED_STATUSES = frozenset(
    {OrderStatus.ASSIGNED, OrderStatus.IN_PROGRESS, OrderStatus.COMPLETED, OrderStatus.CANCELLED}
)


@router.get("/{order_id}/disputes", response_model=list[DisputeOut])
def list_order_disputes(
    order_id: int = Path(..., le=MAX_DB_INT),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order, _ = _order_for_participant(order_id, user, db)
    rows = db.scalars(
        select(Dispute).where(Dispute.order_id == order.id).order_by(Dispute.id.desc())
    ).all()
    return rows


@router.post(
    "/{order_id}/dispute", response_model=DisputeOut, status_code=status.HTTP_201_CREATED
)
def create_dispute(
    data: DisputeCreate,
    order_id: int = Path(..., le=MAX_DB_INT),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order, can_write = _order_for_participant(order_id, user, db)
    if not can_write:
        raise HTTPException(status.HTTP_403_FORBIDDEN, PARTICIPANT_FORBIDDEN)
    if order.status not in _DISPUTE_ALLOWED_STATUSES:
        raise HTTPException(status.HTTP_409_CONFLICT, DISPUTE_WRONG_STATUS)

    existing_open = db.scalar(
        select(Dispute).where(
            Dispute.order_id == order.id, Dispute.status == DisputeStatus.OPEN
        )
    )
    if existing_open is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, DISPUTE_ALREADY_OPEN)

    dispute = Dispute(order_id=order.id, raised_by=user.id, reason=data.reason)
    db.add(dispute)
    db.flush()
    _notify_admins_of_dispute(db, user, dispute, order)
    db.commit()
    db.refresh(dispute)
    return dispute

