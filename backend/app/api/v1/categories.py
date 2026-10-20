from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Category
from app.schemas.category import CategoryOut

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=list[CategoryOut])
def list_categories(db: Session = Depends(get_db)):
    """Ommaviy: faqat faol kategoriyalar, nom bo'yicha."""
    return db.scalars(
        select(Category).where(Category.is_active.is_(True)).order_by(Category.name, Category.id)
    ).all()
