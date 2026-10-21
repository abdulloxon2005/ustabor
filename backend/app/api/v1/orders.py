from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy import exists, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_role
from app.core.config import MAX_DB_INT, settings
from app.db.session import get_db
from app.models import Category, MasterProfile, MasterService, Order, OrderOffer, OrderStatusHistory, Quote, Review, User
from app.models.enums import OfferStatus, OrderStatus, Role, SelectionMode
from app.schemas.order import (
    OfferOut,
    OrderCompleteOut,
    OrderCreate,
    OrderDetailOut,
    OrderListItem,
    OrderOut,
    SelectMasterIn,
)
from app.schemas.quote import QuoteIn, QuoteOut
from app.schemas.review import OrderReviewOut, ReviewCreate, ReviewOut
from app.services import matching, pricing, reviews
from app.services.order_flow import assign_master, create_order_history, transition

router = APIRouter(prefix="/orders", tags=["orders"])

_ORDER_OPTS = (
    selectinload(Order.history),
    selectinload(Order.category),
    selectinload(Order.offers),
    selectinload(Order.quotes),
    selectinload(Order.master).selectinload(MasterProfile.user),
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
    review_out = OrderReviewOut(rating=rev.rating, comment=rev.comment, created_at=rev.created_at) if rev else None
    can_review = bool(order.status == OrderStatus.COMPLETED and rev is None)

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
        selection_mode=SelectionMode(data.selection_mode),
        master_id=None,
        agreed_price=None,
        commission_rate=settings.COMMISSION_RATE,
        commission_amount=None,
    )
    db.add(order)
    db.flush()
    create_order_history(db, order, user)

    note = None
    if order.selection_mode == SelectionMode.AUTOMATIC:
        matching.expire_stale_offers(db)
        offer = matching.offer_next(db, order, user)
        if offer is None:
            note = "Mos usta topilmadi"

    db.commit()
    db.refresh(order)
    return _order_out(_own_order(order.id, user, db), db, note=note)


@router.get("", response_model=list[OrderListItem])
def list_orders(
    status_filter: OrderStatus | None = None,
    limit: int = 20,
    offset: int = Query(default=0, le=MAX_DB_INT),
    user: User = Depends(require_role(Role.CUSTOMER)),
    db: Session = Depends(get_db),
):
    matching.expire_stale_offers(db)
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


@router.get("/{order_id}", response_model=OrderDetailOut)
def get_order(
    order_id: int = Path(..., le=MAX_DB_INT),
    user: User = Depends(require_role(Role.CUSTOMER)),
    db: Session = Depends(get_db),
):
    db.expire_all()
    matching.expire_stale_offers(db)
    db.commit()
    order = _own_order(order_id, user, db)
    return _order_detail_out(order, db)


@router.post("/{order_id}/cancel", response_model=OrderOut)
def cancel_order(
    order_id: int = Path(..., le=MAX_DB_INT),
    user: User = Depends(require_role(Role.CUSTOMER)),
    db: Session = Depends(get_db),
):
    order = _own_order(order_id, user, db)
    transition(db, order, OrderStatus.CANCELLED, user)
    db.commit()
    db.refresh(order)
    return _order_out(_own_order(order.id, user, db), db)


# ---------- Manual usta tanlash ----------


@router.post("/{order_id}/select-master")
def select_master(
    data: SelectMasterIn,
    order_id: int = Path(..., le=MAX_DB_INT),
    user: User = Depends(require_role(Role.CUSTOMER)),
    db: Session = Depends(get_db),
):
    # Muddati o'tgan takliflarni belgilash
    matching.expire_stale_offers(db)
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
        next_offer = matching.offer_next(db, order, user)
        next_offered = next_offer is not None

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
    )
    db.commit()
    db.refresh(rev)
    return rev

