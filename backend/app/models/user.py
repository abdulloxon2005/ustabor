from typing import Optional

from sqlalchemy import Boolean, String, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdTimestampMixin
from app.models.enums import Role, enum_type


class User(IdTimestampMixin, Base):
    __tablename__ = "users"

    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[Role] = mapped_column(enum_type(Role))
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=true()
    )

    # Faqat role=master bo'lgan foydalanuvchida bo'ladi
    master_profile: Mapped[Optional["MasterProfile"]] = relationship(
        back_populates="user", uselist=False
    )