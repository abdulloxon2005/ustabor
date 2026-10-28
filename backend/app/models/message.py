from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdTimestampMixin


class OrderMessage(IdTimestampMixin, Base):
    """Buyurtma ichidagi mijoz <-> usta yozishmasi.

    Faqat order.customer_id yoki biriktirilgan ustaning useri yoza/o'qiy oladi
    (admin faqat o'qish uchun) — tekshiruv app/api/v1/orders.py da.
    """

    __tablename__ = "order_messages"

    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    sender_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)

    order: Mapped["Order"] = relationship(back_populates="messages")
