from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdTimestampMixin
from app.models.enums import DisputeStatus, enum_type


class Dispute(IdTimestampMixin, Base):
    """Mijoz yoki usta tomonidan buyurtma bo'yicha yoki umumiy bildirilgan shikoyat.
    Faqat admin hal qiladi (status_history kabi order.status ga ta'sir qilmaydi).
    """

    __tablename__ = "disputes"

    order_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=True
    )
    raised_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[DisputeStatus] = mapped_column(
        enum_type(DisputeStatus), default=DisputeStatus.OPEN
    )
    admin_note: Mapped[Optional[str]] = mapped_column(Text)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    order: Mapped[Optional["Order"]] = relationship(back_populates="disputes")
