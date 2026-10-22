import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import Role

PHONE_ERROR = "Telefon raqami noto'g'ri. Namuna: +998901234567"


def normalize_phone(raw: str) -> str:
    """'90 123-45-67', '998901234567', '+998901234567' -> '+998901234567'."""
    if not isinstance(raw, str):
        raise ValueError(PHONE_ERROR)
    s = raw.strip()
    # Faqat bo'shliq, tire va qavslar ruxsat; boshqa belgilar xato
    if not re.fullmatch(r"\+?[\d\s\-()]+", s):
        raise ValueError(PHONE_ERROR)
    digits = re.sub(r"\D", "", s)
    if len(digits) == 9:
        digits = "998" + digits
    if not (len(digits) == 12 and digits.startswith("998")):
        raise ValueError(PHONE_ERROR)
    return "+" + digits


class RegisterRequest(BaseModel):
    # Noma'lum maydonlar (is_active, is_approved...) e'tiborga olinmaydi
    phone: str
    password: str = Field(min_length=8, max_length=72)
    full_name: str = Field(min_length=2, max_length=120)
    role: Literal["customer", "master"]

    @field_validator("phone")
    @classmethod
    def _phone(cls, v: str) -> str:
        return normalize_phone(v)

    @field_validator("full_name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Ism kamida 2 ta belgidan iborat bo'lishi kerak")
        return v

    @field_validator("password")
    @classmethod
    def _password(cls, v: str) -> str:
        if not any(c.isalpha() for c in v) or not any(c.isdigit() for c in v):
            raise ValueError("Parol kamida bitta harf va bitta raqamdan iborat bo'lishi kerak")
        return v


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=72)

    @field_validator("new_password")
    @classmethod
    def _new_password(cls, v: str) -> str:
        if not any(c.isalpha() for c in v) or not any(c.isdigit() for c in v):
            raise ValueError("Yangi parol kamida bitta harf va bitta raqamdan iborat bo'lishi kerak")
        return v


class LoginRequest(BaseModel):
    phone: str
    password: str = Field(min_length=1, max_length=128)

    @field_validator("phone")
    @classmethod
    def _phone(cls, v: str) -> str:
        return normalize_phone(v)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    phone: str
    full_name: str
    role: Role
    is_active: bool


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
