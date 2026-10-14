from typing import Optional

from sqlalchemy import (
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdTimestampMixin
from app.models.enums import PricingType, enum_type


class MasterProfile(IdTimestampMixin, Base):
    __tablename__ = "master_profiles"
    __table_args__ = (
        Index("ix_master_profiles_city_district", "city", "district"),
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    bio: Mapped[str] = mapped_column(Text, default="", server_default="")
    city: Mapped[str] = mapped_column(String(80))
    district: Mapped[str] = mapped_column(String(80))
    is_available: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=true()
    )
    # Admin tasdiqlamaguncha usta ro'yxatda ko'rinmaydi
    is_approved: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false()
    )
    rating_avg: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    rating_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    user: Mapped["User"] = relationship(back_populates="master_profile")
    services: Mapped[list["MasterService"]] = relationship(
        back_populates="master", cascade="all, delete-orphan"
    )


class MasterService(IdTimestampMixin, Base):
    __tablename__ = "master_services"
    __table_args__ = (
        UniqueConstraint(
            "master_id", "category_id", name="uq_master_services_master_category"
        ),
    )

    master_id: Mapped[int] = mapped_column(
        ForeignKey("master_profiles.id", ondelete="CASCADE")
    )
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    pricing_type: Mapped[PricingType] = mapped_column(enum_type(PricingType))
    # So'mda, butun son. quote turida bo'sh bo'lishi mumkin
    base_price: Mapped[Optional[int]] = mapped_column(Integer)

    master: Mapped["MasterProfile"] = relationship(back_populates="services")
    category: Mapped["Category"] = relationship()