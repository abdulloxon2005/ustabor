from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import settings
from app.db.base import Base, IdTimestampMixin
from app.models.enums import (
    OfferStatus,
    OrderStatus,
    QuoteStatus,
    SelectionMode,
    enum_type,
)


class Order(IdTimestampMixin, Base):
    __tablename__ = "orders"

    customer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    # Biriktirilgunga qadar bo'sh
    master_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("master_profiles.id"), index=True
    )

    description: Mapped[str] = mapped_column(Text)
    city: Mapped[str] = mapped_column(String(80))
    district: Mapped[str] = mapped_column(String(80))
    address: Mapped[str] = mapped_column(String(255))

    status: Mapped[OrderStatus] = mapped_column(
        enum_type(OrderStatus), default=OrderStatus.SEARCHING, index=True
    )
    selection_mode: Mapped[SelectionMode] = mapped_column(enum_type(SelectionMode))

    # Pul: butun so'mda, float yo'q
    agreed_price: Mapped[Optional[int]] = mapped_column(Integer)
    # Buyurtma yaratilganda nusxalanadi: foiz o'zgarsa eski hisob buzilmaydi
    commission_rate: Mapped[int] = mapped_column(
        Integer, default=lambda: settings.COMMISSION_RATE, server_default="10"
    )
    commission_amount: Mapped[Optional[int]] = mapped_column(Integer)

    customer: Mapped["User"] = relationship()
    category: Mapped["Category"] = relationship()
    master: Mapped[Optional["MasterProfile"]] = relationship()
    history: Mapped[list["OrderStatusHistory"]] = relationship(
        back_populates="order", order_by="OrderStatusHistory.id"
    )
    offers: Mapped[list["OrderOffer"]] = relationship(back_populates="order")
    quotes: Mapped[list["Quote"]] = relationship(back_populates="order")


class OrderOffer(IdTimestampMixin, Base):
    """Buyurtmaning ustaga taklifi (manual: mijoz tanlaydi, automatic: tizim)."""

    __tablename__ = "order_offers"
    __table_args__ = (
        UniqueConstraint("order_id", "master_id", name="uq_order_offers_order_master"),
    )

    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    master_id: Mapped[int] = mapped_column(ForeignKey("master_profiles.id"))
    status: Mapped[OfferStatus] = mapped_column(
        enum_type(OfferStatus), default=OfferStatus.PENDING
    )
    # So'rov kelganda tekshiriladi, fon vazifasi yo'q
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    order: Mapped["Order"] = relationship(back_populates="offers")


class Quote(IdTimestampMixin, Base):
    """Usta narx taklifi; mijoz tasdiqlagach orders.agreed_price ga o'tadi."""

    __tablename__ = "quotes"

    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    master_id: Mapped[int] = mapped_column(ForeignKey("master_profiles.id"))
    price: Mapped[int] = mapped_column(Integer)
    note: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[QuoteStatus] = mapped_column(
        enum_type(QuoteStatus), default=QuoteStatus.PROPOSED
    )

    order: Mapped["Order"] = relationship(back_populates="quotes")


class OrderStatusHistory(IdTimestampMixin, Base):
    """Har bir holat o'zgarishi shu yerga yoziladi (services/order_flow.py)."""

    __tablename__ = "order_status_history"

    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    # Birinchi yozuvda from_status bo'sh
    from_status: Mapped[Optional[OrderStatus]] = mapped_column(enum_type(OrderStatus))
    to_status: Mapped[OrderStatus] = mapped_column(enum_type(OrderStatus))
    changed_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))

    order: Mapped["Order"] = relationship(back_populates="history")