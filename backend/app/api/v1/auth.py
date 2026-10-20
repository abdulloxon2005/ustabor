from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models import User
from app.models.enums import Role
from app.schemas.auth import LoginRequest, RegisterRequest, TokenOut, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])

PHONE_TAKEN = "Bu telefon raqami allaqachon ro'yxatdan o'tgan"
LOGIN_FAILED = "Telefon yoki parol noto'g'ri"

# Telefon topilmaganda ham xesh tekshiriladi: javob vaqti farq qilmasligi uchun
_DUMMY_HASH = hash_password("dummy-password-for-timing")


def _token_response(user: User) -> TokenOut:
    return TokenOut(
        access_token=create_access_token(user.id),
        user=UserOut.model_validate(user),
    )


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def register(data: RegisterRequest, db: Session = Depends(get_db)):
    if db.scalar(select(User.id).where(User.phone == data.phone)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, PHONE_TAKEN)

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


@router.post("/login", response_model=TokenOut)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.phone == data.phone))
    if user is None:
        verify_password(data.password, _DUMMY_HASH)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, LOGIN_FAILED)
    if not verify_password(data.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, LOGIN_FAILED)
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Akkaunt bloklangan")
    return _token_response(user)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
