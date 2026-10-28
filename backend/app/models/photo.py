from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdTimestampMixin


class OrderPhoto(IdTimestampMixin, Base):
    """Mijoz buyurtmaga qo'shgan rasm (muammoni ko'rsatish uchun).
    Fayl haqiqatda app/services/storage.py orqali diskka saqlanadi.
    """

    __tablename__ = "order_photos"

    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    # uploads/ ga nisbatan yo'l, masalan "order_photos/ab12cd34.jpg"
    file_path: Mapped[str] = mapped_column(String(255))

    order: Mapped["Order"] = relationship(back_populates="photos")


class MasterPhoto(IdTimestampMixin, Base):
    """Usta portfolio rasmi."""

    __tablename__ = "master_photos"

    master_id: Mapped[int] = mapped_column(
        ForeignKey("master_profiles.id", ondelete="CASCADE")
    )
    file_path: Mapped[str] = mapped_column(String(255))

    master: Mapped["MasterProfile"] = relationship(back_populates="photos")
