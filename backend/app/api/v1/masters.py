from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy import exists, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_role
from app.db.session import get_db
from app.models import Category, MasterProfile, MasterService, User
from app.models.enums import PricingType, Role
from app.schemas.master import (
    AvailabilityIn,
    MasterMeOut,
    MasterPublicOut,
    ProfileCreate,
    ProfileUpdate,
    ServiceIn,
    ServiceOut,
)

router = APIRouter(prefix="/masters", tags=["masters"])

NO_PROFILE = "Usta profili topilmadi. Avval profil yarating"
_with_services = selectinload(MasterProfile.services).selectinload(MasterService.category)


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
        select(MasterProfile).where(MasterProfile.user_id == user.id).options(_with_services)
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


# ---------- Ommaviy ro'yxat ----------

@router.get("", response_model=list[MasterPublicOut])
def list_masters(
    category_id: int | None = None,
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
        .options(_with_services, selectinload(MasterProfile.user))
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
def get_master(master_id: int, db: Session = Depends(get_db)):
    """Tasdiqlangan usta band bo'lsa ham ko'rinadi; tasdiqlanmagan/bloklangan -> 404."""
    profile = db.scalar(
        select(MasterProfile)
        .join(User, User.id == MasterProfile.user_id)
        .where(
            MasterProfile.id == master_id,
            MasterProfile.is_approved.is_(True),
            User.is_active.is_(True),
        )
        .options(_with_services, selectinload(MasterProfile.user))
    )
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usta topilmadi")
    return _public(profile)
