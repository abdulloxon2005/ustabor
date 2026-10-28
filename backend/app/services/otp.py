"""Tasdiqlash kodi (OTP): yaratish, SMS (mock) orqali yuborish, tekshirish.

Diqqat — bu modul COMMIT QILMAYDI qoidasidan ataylab chetga chiqadi: noto'g'ri
kod kiritilganda urinishlar soni (attempts) darhol saqlanishi kerak, aks holda
chaqiruvchi endpoint xatolik bilan to'xtab, commit qilinmay qoladi va hisoblagich
yo'qoladi (brute-force himoyasi ishlamay qoladi). Shu sababli verify_otp xato
holatda o'zi db.commit() qiladi.
"""

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.models import OtpCode
from app.models.enums import OtpPurpose
from app.services import sms

OTP_TTL_MINUTES = 10
OTP_MAX_ATTEMPTS = 5
OTP_REQUEST_WINDOW_MINUTES = 5
OTP_REQUEST_MAX_PER_WINDOW = 3

INVALID_OR_EXPIRED = "Tasdiqlash kodi yaroqsiz yoki muddati tugagan"
WRONG_CODE = "Tasdiqlash kodi noto'g'ri"
TOO_MANY_REQUESTS = "Juda ko'p so'rov yuborildi. Birozdan so'ng qayta urining"


def _generate_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def _aware(dt: datetime) -> datetime:
    """SQLite ba'zan tzinfo'siz datetime qaytaradi; UTC deb hisoblaymiz."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def request_otp(db: Session, phone: str, purpose: OtpPurpose) -> None:
    """Yangi kod yaratadi va (mock) SMS yuboradi. COMMIT QILMAYDI.

    Bir xil raqam/maqsad uchun oxirgi OTP_REQUEST_WINDOW_MINUTES daqiqada
    OTP_REQUEST_MAX_PER_WINDOW martadan ko'p so'rov bo'lsa -> 429.
    """
    window_start = datetime.now(timezone.utc) - timedelta(minutes=OTP_REQUEST_WINDOW_MINUTES)
    recent = db.scalar(
        select(func.count(OtpCode.id)).where(
            OtpCode.phone == phone,
            OtpCode.purpose == purpose,
            OtpCode.created_at >= window_start,
        )
    )
    if recent and recent >= OTP_REQUEST_MAX_PER_WINDOW:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, TOO_MANY_REQUESTS)

    code = _generate_code()
    otp = OtpCode(
        phone=phone,
        code_hash=hash_password(code),
        purpose=purpose,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=OTP_TTL_MINUTES),
    )
    db.add(otp)
    db.flush()
    sms.send_sms(phone, f"UstaBor tasdiqlash kodi: {code}")


def verify_otp(db: Session, phone: str, purpose: OtpPurpose, code: str) -> None:
    """Eng oxirgi, iste'mol qilinmagan kodni tekshiradi va consumed deb belgilaydi.

    Muvaffaqiyat: COMMIT QILMAYDI (chaqiruvchi o'z amali bilan birga commit qiladi).
    Xatolik: o'zi commit qiladi (attempts hisoblagichi saqlanishi uchun) va
    HTTPException ko'taradi (400 yoki 429).
    """
    otp = db.scalar(
        select(OtpCode)
        .where(
            OtpCode.phone == phone,
            OtpCode.purpose == purpose,
            OtpCode.consumed_at.is_(None),
        )
        .order_by(OtpCode.id.desc())
    )
    now = datetime.now(timezone.utc)

    if otp is None or _aware(otp.expires_at) < now:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, INVALID_OR_EXPIRED)

    if otp.attempts >= OTP_MAX_ATTEMPTS:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, TOO_MANY_REQUESTS)

    if not verify_password(code, otp.code_hash):
        otp.attempts += 1
        db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, WRONG_CODE)

    otp.consumed_at = now
    db.flush()
