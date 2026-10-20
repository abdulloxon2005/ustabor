from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import OrderStatus, SelectionMode
from app.schemas.quote import QuoteOut


def _clean(v: str, label: str) -> str:
    v = v.strip()
    if not v:
        raise ValueError(f"{label} bo'sh bo'lmasligi kerak")
    return v


class OrderCreate(BaseModel):
    """Himoyalangan maydonlar yo'q: status, master_id, agreed_price, commission_*."""

    category_id: int
    description: str = Field(min_length=5, max_length=2000)
    city: str = Field(min_length=1, max_length=80)
    district: str = Field(min_length=1, max_length=80)
    address: str = Field(min_length=1, max_length=255)
    selection_mode: Literal["manual", "automatic"]

    @field_validator("description")
    @classmethod
    def _desc(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 5:
            raise ValueError("Tavsif kamida 5 ta belgidan iborat bo'lishi kerak")
        return v

    @field_validator("city")
    @classmethod
    def _city(cls, v: str) -> str:
        return _clean(v, "Shahar")

    @field_validator("district")
    @classmethod
    def _district(cls, v: str) -> str:
        return _clean(v, "Tuman")

    @field_validator("address")
    @classmethod
    def _address(cls, v: str) -> str:
        return _clean(v, "Manzil")


class SelectMasterIn(BaseModel):
    master_id: int


class HistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    from_status: OrderStatus | None
    to_status: OrderStatus
    changed_by: int | None
    created_at: datetime


class OfferOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    master_id: int
    master_name: str
    master_full_name: str = ""
    status: str
    expires_at: datetime | None


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_id: int
    category_id: int
    category_name: str
    master_id: int | None
    master_name: str | None = None
    master_full_name: str | None = None
    description: str
    city: str
    district: str
    address: str
    status: OrderStatus
    selection_mode: SelectionMode
    agreed_price: int | None
    commission_rate: int
    commission_amount: int | None
    created_at: datetime
    history: list[HistoryOut]
    offers: list[OfferOut] = []
    note: str | None = None


class OrderListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category_id: int
    category_name: str
    description: str
    city: str
    district: str
    status: OrderStatus
    selection_mode: SelectionMode
    agreed_price: int | None
    master_id: int | None = None
    master_name: str | None = None
    master_full_name: str | None = None
    created_at: datetime
    offers: list[OfferOut] = []
    quotes: list[QuoteOut] = []


class OrderDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_id: int
    category_id: int
    category_name: str
    master_id: int | None
    master_name: str | None = None
    master_full_name: str | None = None
    description: str
    city: str
    district: str
    address: str
    status: OrderStatus
    selection_mode: SelectionMode
    agreed_price: int | None = None
    final_price: int | None = None
    commission_rate: int
    quotes: list[QuoteOut] = []
    created_at: datetime
    history: list[HistoryOut] = []
    offers: list[OfferOut] = []
    note: str | None = None


class OrderCompleteOut(BaseModel):
    order_id: int
    status: OrderStatus
    price: int
    commission_rate: int
    commission_amount: int
    net_amount: int
    net: int
    detail: str = "Buyurtma muvaffaqiyatli yakunlandi"
