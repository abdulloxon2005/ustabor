from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, File, HTTPException, Path, Query, UploadFile, status
from sqlalchemy import delete, exists, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_role
from app.core.config import MAX_DB_INT
from app.db.session import get_db
from app.models import Category, Favorite, MasterAvailability, MasterPhoto, MasterProfile, MasterService, Order, OrderOffer, Review, User
from app.models.enums import OfferStatus, OrderStatus, PricingType, QuoteStatus, Role
from app.schemas.master import (
    AvailabilityIn,
    MasterActiveOrderItem,
    MasterEarningOrderItem,
    MasterEarningsOut,
    MasterMeOut,
    MasterOfferItem,
    MasterOrdersOut,
    MasterPublicOut,
    ProfileCreate,
    ProfileUpdate,
    ScheduleDayIn,
    ScheduleDayOut,
    ServiceIn,
    ServiceOut,
)
from app.schemas.photo import PhotoOut
from app.schemas.quote import QuoteOut
from app.schemas.review import MasterReviewItem, MasterReviewsOut
from app.services import matching, storage

router = APIRouter(prefix="/masters", tags=["masters"])

MAX_MASTER_PHOTOS = 10

NO_PROFILE = "Usta profili topilmadi. Avval profil yarating"
_with_services = (
    selectinload(MasterProfile.services).selectinload(MasterService.category),
    selectinload(MasterProfile.photos),
    selectinload(MasterProfile.availability),
)

_DEFAULT_START = "09:00"
_DEFAULT_END = "18:00"


def _schedule_out(profile: MasterProfile) -> list[ScheduleDayOut]:
    """7 kunlik jadval: belgilanmagan kunlar uchun standart (ish kuni, 09:00-18:00)."""
    by_weekday = {a.weekday: a for a in (profile.availability or [])}
    return [
        ScheduleDayOut.model_validate(by_weekday[d])
        if d in by_weekday
        else ScheduleDayOut(weekday=d, is_working=True, start_time=_DEFAULT_START, end_time=_DEFAULT_END)
        for d in range(7)
    ]


def _services_out(profile: MasterProfile, only_active: bool) -> list[ServiceOut]:
    items = [
        ServiceOut(
            category_id=s.category_id,
            category_name=s.category.name,
            pricing_type=s.pricing_type,
            base_price=s.base_price,
        )
        for s in sorted(profile.services, key=lambda s: s.category.name)
        if s.category.is_active or not only_active
    ]
    return items


def _public(profile: MasterProfile) -> MasterPublicOut:
    return MasterPublicOut(
        id=profile.id,
        full_name=profile.user.full_name,
        bio=profile.bio,
        city=profile.city,
        district=profile.district,
        is_available=profile.is_available,
        rating_avg=profile.rating_avg,
        rating_count=profile.rating_count,
        services=_services_out(profile, only_active=True),
        photos=[
            PhotoOut(id=p.id, url=storage.url_for(p.file_path), created_at=p.created_at)
            for p in (profile.photos or [])
        ],
        schedule=_schedule_out(profile),
    )


def _me(profile: MasterProfile) -> MasterMeOut:
    return MasterMeOut(
        **_public(profile).model_dump(exclude={"services"}),
        services=_services_out(profile, only_active=False),
        is_approved=profile.is_approved,
    )


def _own_profile(db: Session, user: User) -> MasterProfile:
    """Faqat chaqiruvchining o'z profili (id so'rovdan olinmaydi)."""
    profile = db.scalar(
        select(MasterProfile).where(MasterProfile.user_id == user.id).options(*_with_services)
    )
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NO_PROFILE)
    return profile


# ---------- Usta o'zi (MASTER roli) ----------
# Diqqat: /me yo'llari /{master_id} dan OLDIN e'lon qilinadi.

@router.post("/profile", response_model=MasterMeOut, status_code=status.HTTP_201_CREATED)
def create_profile(
    data: ProfileCreate,
    user: User = Depends(require_role(Role.MASTER)),
    db: Session = Depends(get_db),
):
    exists_msg = "Sizda usta profili allaqachon mavjud"
    if db.scalar(select(MasterProfile.id).where(MasterProfile.user_id == user.id)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, exists_msg)
    profile = MasterProfile(
        user_id=user.id,
        bio=data.bio,
        city=data.city,
        district=data.district,
        is_approved=False,
        is_available=True,
    )
    db.add(profile)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, exists_msg)
    return _me(_own_profile(db, user))


@router.get("/me", response_model=MasterMeOut)
def get_my_profile(
    user: User = Depends(require_role(Role.MASTER)), db: Session = Depends(get_db)
):
    return _me(_own_profile(db, user))


@router.patch("/me", response_model=MasterMeOut)
def update_my_profile(
    data: ProfileUpdate,
    user: User = Depends(require_role(Role.MASTER)),
    db: Session = Depends(get_db),
):
    profile = _own_profile(db, user)
    for field in data.model_fields_set:
        setattr(profile, field, getattr(data, field))
    db.commit()
    return _me(_own_profile(db, user))


@router.put("/me/services", response_model=MasterMeOut)
def replace_my_services(
    items: list[ServiceIn] = Body(...),
    user: User = Depends(require_role(Role.MASTER)),
    db: Session = Depends(get_db),
):
    profile = _own_profile(db, user)

    ids = [i.category_id for i in items]
    if len(ids) != len(set(ids)):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Bir kategoriya ro'yxatda faqat bir marta bo'lishi mumkin",
        )
    active_ids = set(
        db.scalars(
            select(Category.id).where(Category.id.in_(ids), Category.is_active.is_(True))
        )
    )
    if set(ids) - active_ids:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Kategoriya topilmadi yoki faol emas",
        )

    # Avval eskilarini o'chirib flush qilamiz (unique cheklov buzilmasligi uchun)
    profile.services.clear()
    db.flush()
    for i in items:
        profile.services.append(
            MasterService(
                category_id=i.category_id,
                pricing_type=PricingType(i.pricing_type),
                base_price=i.base_price,
            )
        )
    db.commit()
    return _me(_own_profile(db, user))


@router.patch("/me/availability", response_model=MasterMeOut)
def set_availability(
    data: AvailabilityIn,
    user: User = Depends(require_role(Role.MASTER)),
    db: Session = Depends(get_db),
):
    profile = _own_profile(db, user)
    profile.is_available = data.is_available
    db.commit()
    return _me(_own_profile(db, user))


# ---------- Haftalik ish jadvali (faqat ko'rsatish uchun) ----------


@router.get("/me/schedule", response_model=list[ScheduleDayOut])
def get_my_schedule(
    user: User = Depends(require_role(Role.MASTER)),
    db: Session = Depends(get_db),
):
    profile = _own_profile(db, user)
    return _schedule_out(profile)


@router.put("/me/schedule", response_model=list[ScheduleDayOut])
def set_my_schedule(
    days: list[ScheduleDayIn] = Body(...),
    user: User = Depends(require_role(Role.MASTER)),
    db: Session = Depends(get_db),
):
    profile = _own_profile(db, user)

    weekdays = [d.weekday for d in days]
    if len(weekdays) != len(set(weekdays)):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Bir kun ro'yxatda faqat bir marta bo'lishi mumkin",
        )

    # Avval eskilarini o'chirib flush qilamiz (unique cheklov buzilmasligi uchun)
    profile.availability.clear()
    db.flush()
    for d in days:
        profile.availability.append(
            MasterAvailability(
                weekday=d.weekday,
                is_working=d.is_working,
                start_time=d.start_time,
                end_time=d.end_time,
            )
        )
    db.commit()
    return _schedule_out(_own_profile(db, user))


# ---------- Portfolio rasmlari ----------


@router.post(
    "/me/photos", response_model=list[PhotoOut], status_code=status.HTTP_201_CREATED
)
async def upload_my_photos(
    files: list[UploadFile] = File(...),
    user: User = Depends(require_role(Role.MASTER)),
    db: Session = Depends(get_db),
):
    profile = _own_profile(db, user)

    existing = db.scalar(
        select(func.count(MasterPhoto.id)).where(MasterPhoto.master_id == profile.id)
    )
    if (existing or 0) + len(files) > MAX_MASTER_PHOTOS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Portfolioga ko'pi bilan {MAX_MASTER_PHOTOS} ta rasm yuklash mumkin",
        )

    saved: list[MasterPhoto] = []
    for f in files:
        rel_path = await storage.save_image(f, "master_photos")
        photo = MasterPhoto(master_id=profile.id, file_path=rel_path)
        db.add(photo)
        saved.append(photo)
    db.commit()
    for p in saved:
        db.refresh(p)

    return [
        PhotoOut(id=p.id, url=storage.url_for(p.file_path), created_at=p.created_at)
        for p in saved
    ]


@router.delete("/me/photos/{photo_id}")
def delete_my_photo(
    photo_id: int = Path(..., le=MAX_DB_INT),
    user: User = Depends(require_role(Role.MASTER)),
    db: Session = Depends(get_db),
):
    profile = _own_profile(db, user)
    photo = db.get(MasterPhoto, photo_id)
    if photo is None or photo.master_id != profile.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rasm topilmadi")

    storage.delete_image(photo.file_path)
    db.delete(photo)
    db.commit()
    return {"detail": "Rasm o'chirildi"}


def _is_expired(expires_at: datetime | None) -> bool:
    if expires_at is None:
        return False
    now = datetime.now(timezone.utc)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at < now


@router.get("/me/orders", response_model=MasterOrdersOut)
def get_my_orders(
    user: User = Depends(require_role(Role.MASTER)),
    db: Session = Depends(get_db),
):
    profile = _own_profile(db, user)
    matching.rotate_stale_automatic_orders(db)
    db.commit()

    offers_stmt = (
        select(OrderOffer)
        .join(Order, Order.id == OrderOffer.order_id)
        .where(
            OrderOffer.master_id == profile.id,
            OrderOffer.status == OfferStatus.PENDING,
            Order.status == OrderStatus.SEARCHING,
        )
        .options(
            selectinload(OrderOffer.order).selectinload(Order.category),
        )
        .order_by(OrderOffer.id.desc())
    )
    raw_offers = db.scalars(offers_stmt).all()
    pending_offers = [
        MasterOfferItem(
            id=o.id,
            order_id=o.order_id,
            category_id=o.order.category_id,
            category_name=o.order.category.name,
            description=o.order.description,
            city=o.order.city,
            district=o.order.district,
            expires_at=o.expires_at,
            created_at=o.created_at,
        )
        for o in raw_offers
        if not _is_expired(o.expires_at)
    ]

    active_orders_stmt = (
        select(Order)
        .where(
            Order.master_id == profile.id,
            Order.status.in_([OrderStatus.ASSIGNED, OrderStatus.IN_PROGRESS]),
        )
        .options(
            selectinload(Order.category),
            selectinload(Order.customer),
            selectinload(Order.quotes),
        )
        .order_by(Order.id.desc())
    )
    active_orders_list = db.scalars(active_orders_stmt).all()
    active_orders = []
    for o in active_orders_list:
        latest_proposed = next(
            (
                QuoteOut.model_validate(q)
                for q in sorted(o.quotes or [], key=lambda x: x.id, reverse=True)
                if q.status == QuoteStatus.PROPOSED
            ),
            None,
        )
        active_orders.append(
            MasterActiveOrderItem(
                id=o.id,
                category_id=o.category_id,
                category_name=o.category.name,
                description=o.description,
                city=o.city,
                district=o.district,
                address=o.address,
                customer_name=o.customer.full_name if o.customer else "",
                customer_full_name=o.customer.full_name if o.customer else "",
                status=o.status,
                agreed_price=o.agreed_price,
                latest_quote=latest_proposed,
                latest_proposed_quote=latest_proposed,
                created_at=o.created_at,
            )
        )

    return MasterOrdersOut(
        pending_offers=pending_offers,
        offers=pending_offers,
        active_orders=active_orders,
    )


@router.get("/me/earnings", response_model=MasterEarningsOut)
def get_my_earnings(
    user: User = Depends(require_role(Role.MASTER)),
    db: Session = Depends(get_db),
):
    profile = _own_profile(db, user)

    stmt = (
        select(Order)
        .where(
            Order.master_id == profile.id,
            Order.status == OrderStatus.COMPLETED,
        )
        .options(selectinload(Order.category))
        .order_by(Order.id.desc())
    )
    completed_orders = db.scalars(stmt).all()

    completed_count = len(completed_orders)
    gross_total = sum(o.agreed_price or 0 for o in completed_orders)
    commission_total = sum(o.commission_amount or 0 for o in completed_orders)
    net_total = gross_total - commission_total

    recent_orders = [
        MasterEarningOrderItem(
            id=o.id,
            category=o.category.name,
            category_name=o.category.name,
            agreed_price=o.agreed_price or 0,
            commission_amount=o.commission_amount or 0,
            net=(o.agreed_price or 0) - (o.commission_amount or 0),
            net_amount=(o.agreed_price or 0) - (o.commission_amount or 0),
        )
        for o in completed_orders[:20]
    ]

    return MasterEarningsOut(
        completed_count=completed_count,
        gross_total=gross_total,
        commission_total=commission_total,
        net_total=net_total,
        orders=recent_orders,
    )


# ---------- Sevimli ustalar (mijoz) ----------
# Diqqat: /favorites yo'li /{master_id} dan OLDIN e'lon qilinadi.


@router.get("/favorites", response_model=list[MasterPublicOut])
def list_favorites(
    user: User = Depends(require_role(Role.CUSTOMER)),
    db: Session = Depends(get_db),
):
    stmt = (
        select(MasterProfile)
        .join(Favorite, Favorite.master_id == MasterProfile.id)
        .join(User, User.id == MasterProfile.user_id)
        .where(
            Favorite.customer_id == user.id,
            MasterProfile.is_approved.is_(True),
            User.is_active.is_(True),
        )
        .options(*_with_services, selectinload(MasterProfile.user))
        .order_by(Favorite.id.desc())
    )
    return [_public(p) for p in db.scalars(stmt).all()]


@router.post("/{master_id}/favorite", status_code=status.HTTP_201_CREATED)
def add_favorite(
    master_id: int = Path(..., le=MAX_DB_INT),
    user: User = Depends(require_role(Role.CUSTOMER)),
    db: Session = Depends(get_db),
):
    profile = db.get(MasterProfile, master_id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usta topilmadi")

    existing = db.scalar(
        select(Favorite).where(Favorite.customer_id == user.id, Favorite.master_id == master_id)
    )
    if existing is None:
        db.add(Favorite(customer_id=user.id, master_id=master_id))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()  # poygada boshqa so'rov allaqachon qo'shgan: baribir yakuniy holat to'g'ri
    return {"detail": "Sevimlilarga qo'shildi", "is_favorited": True}


@router.delete("/{master_id}/favorite")
def remove_favorite(
    master_id: int = Path(..., le=MAX_DB_INT),
    user: User = Depends(require_role(Role.CUSTOMER)),
    db: Session = Depends(get_db),
):
    db.execute(
        delete(Favorite).where(
            Favorite.customer_id == user.id, Favorite.master_id == master_id
        )
    )
    db.commit()
    return {"detail": "Sevimlilardan olib tashlandi", "is_favorited": False}


# ---------- Ommaviy ro'yxat ----------

@router.get("", response_model=list[MasterPublicOut])
def list_masters(
    category_id: int | None = Query(default=None, le=MAX_DB_INT),
    city: str | None = None,
    district: str | None = None,
    db: Session = Depends(get_db),
):
    stmt = (
        select(MasterProfile)
        .join(User, User.id == MasterProfile.user_id)
        .where(
            MasterProfile.is_approved.is_(True),
            MasterProfile.is_available.is_(True),
            User.is_active.is_(True),
        )
        .options(*_with_services, selectinload(MasterProfile.user))
        .order_by(
            MasterProfile.rating_avg.desc(),
            MasterProfile.rating_count.desc(),
            MasterProfile.id,
        )
    )
    if category_id is not None:
        stmt = stmt.where(
            exists().where(
                MasterService.master_id == MasterProfile.id,
                MasterService.category_id == category_id,
            )
        )
    if city and city.strip():
        stmt = stmt.where(func.lower(MasterProfile.city) == city.strip().lower())
    if district and district.strip():
        stmt = stmt.where(func.lower(MasterProfile.district) == district.strip().lower())
    return [_public(p) for p in db.scalars(stmt).all()]


@router.get("/{master_id}", response_model=MasterPublicOut)
def get_master(
    master_id: int = Path(..., le=MAX_DB_INT),
    db: Session = Depends(get_db),
):
    """Tasdiqlangan usta band bo'lsa ham ko'rinadi; tasdiqlanmagan/bloklangan -> 404."""
    profile = db.scalar(
        select(MasterProfile)
        .join(User, User.id == MasterProfile.user_id)
        .where(
            MasterProfile.id == master_id,
            MasterProfile.is_approved.is_(True),
            User.is_active.is_(True),
        )
        .options(*_with_services, selectinload(MasterProfile.user))
    )
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usta topilmadi")
    return _public(profile)


@router.get("/{master_id}/reviews", response_model=MasterReviewsOut)
def list_master_reviews(
    master_id: int = Path(..., le=MAX_DB_INT),
    limit: int = 20,
    offset: int = Query(default=0, le=MAX_DB_INT),
    db: Session = Depends(get_db),
):
    profile = db.scalar(
        select(MasterProfile)
        .join(User, User.id == MasterProfile.user_id)
        .where(
            MasterProfile.id == master_id,
            MasterProfile.is_approved.is_(True),
            User.is_active.is_(True),
        )
    )
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usta topilmadi")

    limit = min(max(limit, 1), 100)
    offset = min(max(offset, 0), MAX_DB_INT)

    rows = db.execute(
        select(Review, User.full_name)
        .join(User, Review.customer_id == User.id)
        .where(Review.master_id == master_id)
        .order_by(Review.created_at.desc(), Review.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()

    items = []
    for rev, full_name in rows:
        name_parts = (full_name or "").strip().split()
        first_name = name_parts[0] if name_parts else "Mijoz"
        items.append(
            MasterReviewItem(
                rating=rev.rating,
                comment=rev.comment,
                quality_rating=rev.quality_rating,
                timeliness_rating=rev.timeliness_rating,
                price_rating=rev.price_rating,
                created_at=rev.created_at,
                customer_first_name=first_name,
            )
        )

    sub_avgs = db.execute(
        select(
            func.avg(Review.quality_rating),
            func.avg(Review.timeliness_rating),
            func.avg(Review.price_rating),
        ).where(Review.master_id == master_id)
    ).one()
    quality_avg, timeliness_avg, price_avg = sub_avgs

    return MasterReviewsOut(
        rating_avg=profile.rating_avg,
        rating_count=profile.rating_count,
        quality_avg=round(float(quality_avg), 2) if quality_avg is not None else None,
        timeliness_avg=round(float(timeliness_avg), 2) if timeliness_avg is not None else None,
        price_avg=round(float(price_avg), 2) if price_avg is not None else None,
        reviews=items,
        items=items,
    )
