from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, func, true
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PlatformSetting(Base):
    __tablename__ = "platform_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    commission_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    commission_rate: Mapped[int] = mapped_column(Integer, default=10, server_default="10")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
