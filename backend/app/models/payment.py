from sqlalchemy import ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdTimestampMixin
from app.models.enums import PaymentMethod, PaymentStatus, enum_type


class Payment(IdTimestampMixin, Base):
    __tablename__ = "payments"

    # Bitta buyurtmaga bitta to'lov
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), unique=True)
    method: Mapped[PaymentMethod] = mapped_column(
        enum_type(PaymentMethod), default=PaymentMethod.CASH
    )
    amount: Mapped[int] = mapped_column(Integer)
    status: Mapped[PaymentStatus] = mapped_column(
        enum_type(PaymentStatus), default=PaymentStatus.PAID
    )