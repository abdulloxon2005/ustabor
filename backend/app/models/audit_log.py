from typing import Optional

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdTimestampMixin


class AdminAuditLog(IdTimestampMixin, Base):
    """Admin amallari tarixi (kim, nima, qachon). Faqat ko'rsatish/moderatsiya
    uchun — hech qanday biznes mantiqqa ta'sir qilmaydi.
    """

    __tablename__ = "admin_audit_log"

    admin_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    # Masalan: "assign_master", "block_user", "approve_master", "create_category"
    action: Mapped[str] = mapped_column(String(60))
    # Masalan: "order", "user", "master_profile", "category"
    target_type: Mapped[str] = mapped_column(String(40))
    target_id: Mapped[Optional[int]] = mapped_column(Integer)
    detail: Mapped[Optional[str]] = mapped_column(Text)
