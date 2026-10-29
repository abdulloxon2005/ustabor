from typing import Optional

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdTimestampMixin


class MasterAvailability(IdTimestampMixin, Base):
    """Usta haftalik ish jadvalidagi bitta kun (0=Dushanba .. 6=Yakshanba).

    Faqat ko'rsatish uchun — avtomatik tanlash/offer mantig'iga (matching.py)
    ta'sir qilmaydi.
    """

    __tablename__ = "master_availability"
    __table_args__ = (
        UniqueConstraint("master_id", "weekday", name="uq_master_availability_master_weekday"),
    )

    master_id: Mapped[int] = mapped_column(
        ForeignKey("master_profiles.id", ondelete="CASCADE")
    )
    weekday: Mapped[int] = mapped_column(Integer)  # 0=Dushanba ... 6=Yakshanba
    is_working: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    start_time: Mapped[Optional[str]] = mapped_column(String(5))  # "HH:MM"
    end_time: Mapped[Optional[str]] = mapped_column(String(5))

    master: Mapped["MasterProfile"] = relationship(back_populates="availability")
