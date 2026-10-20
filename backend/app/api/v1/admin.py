from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.db.session import get_db
from app.models import Category, MasterProfile
from app.models.enums import Role
from app.schemas.category import CategoryCreate, CategoryOut, CategoryUpdate, slugify
from app.schemas.master import ApprovalIn, ApprovalOut

# Router darajasida: admindan boshqa hech kim kira olmaydi
router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_role(Role.ADMIN))],
)

SLUG_TAKEN = "Bu slug allaqachon mavjud"


@router.post("/categories", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(data: CategoryCreate, db: Session = Depends(get_db)):
    slug = data.slug or slugify(data.name)
    if not slug:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Nomdan slug yasab bo'lmadi, slug ni qo'lda kiriting",
        )
    if db.scalar(select(Category.id).where(Category.slug == slug)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, SLUG_TAKEN)

    category = Category(name=data.name, slug=slug)
    db.add(category)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, SLUG_TAKEN)
    db.refresh(category)
    return category


@router.patch("/categories/{category_id}", response_model=CategoryOut)
def update_category(category_id: int, data: CategoryUpdate, db: Session = Depends(get_db)):
    category = db.get(Category, category_id)
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kategoriya topilmadi")
    if data.name is not None:
        category.name = data.name
    if data.is_active is not None:
        category.is_active = data.is_active
    db.commit()
    db.refresh(category)
    return category


@router.patch("/masters/{profile_id}/approval", response_model=ApprovalOut)
def set_master_approval(profile_id: int, data: ApprovalIn, db: Session = Depends(get_db)):
    profile = db.get(MasterProfile, profile_id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usta topilmadi")
    profile.is_approved = data.is_approved
    db.commit()
    db.refresh(profile)
    return profile
