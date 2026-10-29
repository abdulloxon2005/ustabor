from typing import Optional

from sqlalchemy import CheckConstraint, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdTimestampMixin


class Review(IdTimestampMixin, Base):
    __tablename__ = "reviews"
    __table_args__ = (
        CheckConstraint("rating >= 1 AND rating <= 5", name="rating_range"),
        CheckConstraint(
            "quality_rating IS NULL OR (quality_rating >= 1 AND quality_rating <= 5)",
            name="quality_rating_range",
        ),
        CheckConstraint(
            "timeliness_rating IS NULL OR (timeliness_rating >= 1 AND timeliness_rating <= 5)",
            name="timeliness_rating_range",
        ),
        CheckConstraint(
            "price_rating IS NULL OR (price_rating >= 1 AND price_rating <= 5)",
            name="price_rating_range",
        ),
    )

    # unique: bitta buyurtmaga bitta sharh
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), unique=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    master_id: Mapped[int] = mapped_column(ForeignKey("master_profiles.id"))
    rating: Mapped[int] = mapped_column(Integer)
    comment: Mapped[Optional[str]] = mapped_column(Text)
    # Ixtiyoriy, batafsil baholash (umumiy "rating"ga ta'sir qilmaydi, faqat ko'rsatish uchun)
    quality_rating: Mapped[Optional[int]] = mapped_column(Integer)
    timeliness_rating: Mapped[Optional[int]] = mapped_column(Integer)
    price_rating: Mapped[Optional[int]] = mapped_column(Integer)