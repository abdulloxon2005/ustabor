from typing import Optional

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, false
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdTimestampMixin


class Notification(IdTimestampMixin, Base):
    """Ilova ichi bildirishnoma. SMS (mock) bilan birga app/services/notify.py
    orqali yaratiladi — qarang: hook nuqtalari matching/order_flow/pricing/admin'da.
    """

    __tablename__ = "notifications"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # Masalan: new_offer, order_assigned, quote_accepted, order_completed, master_approved
    type: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    related_order_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE")
    )
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
