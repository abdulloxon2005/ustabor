from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdTimestampMixin
from app.models.enums import OtpPurpose, enum_type


class OtpCode(IdTimestampMixin, Base):
    """SMS orqali yuboriladigan tasdiqlash kodi (hozircha mock: app/services/sms.py).

    Bitta telefon/maqsad (purpose) uchun bir nechta qator bo'lishi mumkin —
    har doim oxirgi, iste'mol qilinmagan (consumed_at IS NULL) qatorni tekshiramiz.
    """

    __tablename__ = "otp_codes"

    phone: Mapped[str] = mapped_column(String(20), index=True)
    code_hash: Mapped[str] = mapped_column(String(255))
    purpose: Mapped[OtpPurpose] = mapped_column(enum_type(OtpPurpose))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class LoginAttempt(IdTimestampMixin, Base):
    """Muvaffaqiyatsiz login urinishi (brute-force himoyasi, app/api/v1/auth.py).

    Oldingi versiyada xotirada (_failed_attempts dict) saqlanardi: server qayta
    ishga tushsa yoki bir nechta instance bo'lsa ishlamas edi. Endi bazada.
    """

    __tablename__ = "login_attempts"

    phone: Mapped[str] = mapped_column(String(20), index=True)
