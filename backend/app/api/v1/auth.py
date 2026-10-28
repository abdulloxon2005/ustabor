from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models import LoginAttempt, User
from app.models.enums import OtpPurpose, Role
from app.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordConfirm,
    LoginRequest,
    PhoneOnlyRequest,
    RegisterRequest,
    TokenOut,
    UserOut,
)
from app.services import otp as otp_service

router = APIRouter(prefix="/auth", tags=["auth"])

PHONE_TAKEN = "Bu telefon raqami allaqachon ro'yxatdan o'tgan"
LOGIN_FAILED = "Telefon yoki parol noto'g'ri"
OTP_SENT = "Tasdiqlash kodi yuborildi"

# Telefon topilmaganda ham xesh tekshiriladi: javob vaqti farq qilmasligi uchun
_DUMMY_HASH = hash_password("dummy-password-for-timing")

# Brute-force himoyasi: telefon raqami bo'yicha failed attemptlar (DB, app.models.LoginAttempt)
_MAX_FAILED_ATTEMPTS = 5
_BLOCK_WINDOW_SECONDS = 300  # 5 daqiqa


def _token_response(user: User) -> TokenOut:
    return TokenOut(
        access_token=create_access_token(user.id),
        user=UserOut.model_validate(user),
    )


@router.post("/register/request-otp")
def request_register_otp(data: PhoneOnlyRequest, db: Session = Depends(get_db)):
    if db.scalar(select(User.id).where(User.phone == data.phone)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, PHONE_TAKEN)
    otp_service.request_otp(db, data.phone, OtpPurpose.REGISTER)
    db.commit()
    return {"detail": OTP_SENT}


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def register(data: RegisterRequest, db: Session = Depends(get_db)):
    if db.scalar(select(User.id).where(User.phone == data.phone)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, PHONE_TAKEN)

    otp_service.verify_otp(db, data.phone, OtpPurpose.REGISTER, data.otp_code)

    user = User(
        phone=data.phone,
        password_hash=hash_password(data.password),
        full_name=data.full_name,
        role=Role(data.role),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, PHONE_TAKEN)
    db.refresh(user)
    return _token_response(user)


@router.post("/forgot-password/request-otp")
def request_forgot_password_otp(data: PhoneOnlyRequest, db: Session = Depends(get_db)):
    # Mavjud bo'lmagan raqam uchun ham bir xil javob: raqam ro'yxatdan
    # o'tganini bildirib qo'ymaslik uchun (user enumeration oldini olish).
    user = db.scalar(select(User.id).where(User.phone == data.phone))
    if user is not None:
        otp_service.request_otp(db, data.phone, OtpPurpose.RESET)
        db.commit()
    return {"detail": "Agar bu raqam ro'yxatdan o'tgan bo'lsa, tasdiqlash kodi yuborildi"}


@router.post("/forgot-password/confirm")
def confirm_forgot_password(data: ForgotPasswordConfirm, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.phone == data.phone))
    if user is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, otp_service.INVALID_OR_EXPIRED)

    otp_service.verify_otp(db, data.phone, OtpPurpose.RESET, data.otp_code)
    user.password_hash = hash_password(data.new_password)
    db.commit()
    return {"detail": "Parol muvaffaqiyatli tiklandi"}


@router.post("/login", response_model=TokenOut)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    window_start = datetime.now(timezone.utc) - timedelta(seconds=_BLOCK_WINDOW_SECONDS)
    attempt_count = db.scalar(
        select(func.count(LoginAttempt.id)).where(
            LoginAttempt.phone == data.phone,
            LoginAttempt.created_at >= window_start,
        )
    )
    if attempt_count and attempt_count >= _MAX_FAILED_ATTEMPTS:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Juda ko'p muvaffaqiyatsiz urinishlar. Iltimos, 5 daqiqadan so'ng qayta urining",
        )

    def _record_failure() -> None:
        # Darhol commit qilinadi: aks holda 401 javobidan keyin hisoblagich saqlanmaydi.
        db.add(LoginAttempt(phone=data.phone))
        db.commit()

    user = db.scalar(select(User).where(User.phone == data.phone))
    if user is None:
        _record_failure()
        verify_password(data.password, _DUMMY_HASH)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, LOGIN_FAILED)
    if not verify_password(data.password, user.password_hash):
        _record_failure()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, LOGIN_FAILED)
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Akkaunt bloklangan")

    db.execute(delete(LoginAttempt).where(LoginAttempt.phone == data.phone))
    db.commit()
    return _token_response(user)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.post("/change-password")
def change_password(
    data: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Joriy parol noto'g'ri"
        )
    if data.current_password == data.new_password:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Yangi parol joriy parol bilan bir xil bo'lmasligi kerak",
        )
    user.password_hash = hash_password(data.new_password)
    db.commit()
    return {"detail": "Parol muvaffaqiyatli o'zgartirildi"}
