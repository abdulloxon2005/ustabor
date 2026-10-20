"""Sharhlar va reyting xizmati.

Barcha funksiyalar COMMIT QILMAYDI — commit chaqiruvchida.
"""

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import MasterProfile, Order, Review, User
from app.models.enums import OrderStatus


def recompute_master_rating(db: Session, master_profile_id: int) -> MasterProfile:
    """Usta profilining rating_count va rating_avg sini barcha sharhlar
    asosida qayta hisoblaydi va MasterProfile ga yozadi. COMMIT QILMAYDI.
    """
    stmt = select(
        func.count(Review.id).label("count"),
        func.avg(Review.rating).label("avg"),
    ).where(Review.master_id == master_profile_id)

    row = db.execute(stmt).one()
    count = int(row.count or 0)
    avg = round(float(row.avg), 2) if row.avg is not None else 0.0

    master = db.get(MasterProfile, master_profile_id)
    if master is not None:
        master.rating_count = count
        master.rating_avg = avg
        db.flush()
    return master


def create_review(
    db: Session,
    order: Order,
    customer: User | int,
    rating: int,
    comment: str | None = None,
) -> Review:
    """Buyurtmaga sharh qoldirish. COMMIT QILMAYDI.

    Qoidalar:
      - Buyurtma holati COMPLETED bo'lishi shart (aks holda 409)
      - customer order.customer_id ga teng bo'lishi shart (aks holda 403)
      - order.master_id bo'sh bo'lmasligi kerak (aks holda 409)
      - rating 1..5 oralig'idagi butun son (aks holda 422)
      - comment ixtiyoriy, strip qilinadi, maksimal 1000 belgi (aks holda 422)
      - Bitta buyurtmaga bitta sharh (aks holda 409)
      - Unique constraint poygasi (race condition) begin_nested savepoint orqali 409 ga o'giriladi
      - Sharh qo'shilgach recompute_master_rating chaqiriladi
    """
    if order.status != OrderStatus.COMPLETED:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Faqat yakunlangan buyurtmaga sharh qoldirish mumkin",
        )

    customer_id = customer.id if isinstance(customer, User) else customer
    if order.customer_id != customer_id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Bu amal uchun ruxsat yo'q",
        )

    if order.master_id is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Buyurtmaga usta biriktirilmagan",
        )

    if (
        isinstance(rating, bool)
        or not isinstance(rating, int)
        or rating < 1
        or rating > 5
    ):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Baho 1 dan 5 gacha bo'lgan butun son bo'lishi kerak",
        )

    if comment is not None:
        if not isinstance(comment, str):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "Sharh matn bo'lishi kerak",
            )
        comment = comment.strip()
        if not comment:
            comment = None
        elif len(comment) > 1000:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "Sharh 1000 belgidan oshmasligi kerak",
            )

    # Bir buyurtmaga bitta sharh tekshiruvi
    existing = db.scalar(select(Review).where(Review.order_id == order.id))
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Bu buyurtmaga sharh allaqachon qoldirilgan",
        )

    try:
        with db.begin_nested():
            review = Review(
                order_id=order.id,
                customer_id=customer_id,
                master_id=order.master_id,
                rating=rating,
                comment=comment,
            )
            db.add(review)
            db.flush()
    except IntegrityError:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Bu buyurtmaga sharh allaqachon qoldirilgan",
        )

    recompute_master_rating(db, order.master_id)
    return review
