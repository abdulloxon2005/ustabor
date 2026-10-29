from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdTimestampMixin


class Favorite(IdTimestampMixin, Base):
    """Mijozning sevimli ustalar ro'yxatidagi bir yozuvi."""

    __tablename__ = "favorites"
    __table_args__ = (
        UniqueConstraint("customer_id", "master_id", name="uq_favorites_customer_master"),
    )

    customer_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    master_id: Mapped[int] = mapped_column(
        ForeignKey("master_profiles.id", ondelete="CASCADE")
    )
