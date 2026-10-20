from datetime import datetime
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    field_validator,
    model_validator,
)

from app.models.enums import OrderStatus, PricingType
from app.schemas.quote import QuoteOut

MAX_PRICE = 1_000_000_000  # 1 mlrd so'm: aqlga sig'adigan yuqori chegara


def _clean(v: str, label: str) -> str:
    v = v.strip()
    if not v:
        raise ValueError(f"{label} bo'sh bo'lmasligi kerak")
    return v


class ProfileCreate(BaseModel):
    # is_approved va boshqa himoyalangan maydonlar qabul qilinmaydi (e'tiborga olinmaydi)
    bio: str = Field(default="", max_length=1000)
    city: str = Field(min_length=1, max_length=80)
    district: str = Field(min_length=1, max_length=80)

    @field_validator("city")
    @classmethod
    def _city(cls, v: str) -> str:
        return _clean(v, "Shahar")

    @field_validator("district")
    @classmethod
    def _district(cls, v: str) -> str:
        return _clean(v, "Tuman")

    @field_validator("bio")
    @classmethod
    def _bio(cls, v: str) -> str:
        return v.strip()


class ProfileUpdate(BaseModel):
    bio: str | None = Field(default=None, max_length=1000)
    city: str | None = Field(default=None, min_length=1, max_length=80)
    district: str | None = Field(default=None, min_length=1, max_length=80)

    @model_validator(mode="after")
    def _no_nulls(self):
        for f in self.model_fields_set:
            if getattr(self, f) is None:
                raise ValueError("Maydon bo'sh (null) bo'lishi mumkin emas")
        return self

    @field_validator("city")
    @classmethod
    def _city(cls, v: str | None) -> str | None:
        return None if v is None else _clean(v, "Shahar")

    @field_validator("district")
    @classmethod
    def _district(cls, v: str | None) -> str | None:
        return None if v is None else _clean(v, "Tuman")

    @field_validator("bio")
    @classmethod
    def _bio(cls, v: str | None) -> str | None:
        return None if v is None else v.strip()


class ServiceIn(BaseModel):
    category_id: StrictInt
    pricing_type: Literal["fixed", "quote"]
    base_price: StrictInt | None = None

    @model_validator(mode="after")
    def _price_rules(self):
        if self.pricing_type == "fixed":
            if self.base_price is None or self.base_price <= 0:
                raise ValueError("Qat'iy narx uchun narx 0 dan katta bo'lishi kerak")
            if self.base_price > MAX_PRICE:
                raise ValueError("Narx juda katta")
        else:
            self.base_price = None  # quote: narx e'tiborga olinmaydi
        return self


class AvailabilityIn(BaseModel):
    is_available: StrictBool


class ApprovalIn(BaseModel):
    is_approved: StrictBool


class ServiceOut(BaseModel):
    category_id: int
    category_name: str
    pricing_type: PricingType
    base_price: int | None


class MasterPublicOut(BaseModel):
    """Ommaga ko'rinadigan usta: telefon va parol xeshi YO'Q."""

    id: int
    full_name: str
    bio: str
    city: str
    district: str
    is_available: bool
    rating_avg: float
    rating_count: int
    services: list[ServiceOut]


class MasterMeOut(MasterPublicOut):
    is_approved: bool


class ApprovalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_approved: bool


class MasterOfferItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int
    category_id: int
    category_name: str
    description: str
    city: str
    district: str
    expires_at: datetime | None
    created_at: datetime


class MasterActiveOrderItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category_id: int
    category_name: str
    description: str
    city: str
    district: str
    address: str
    customer_name: str
    customer_full_name: str = ""
    status: OrderStatus
    agreed_price: int | None
    latest_quote: QuoteOut | None = None
    latest_proposed_quote: QuoteOut | None = None
    created_at: datetime


class MasterOrdersOut(BaseModel):
    pending_offers: list[MasterOfferItem]
    offers: list[MasterOfferItem] = []
    active_orders: list[MasterActiveOrderItem]


class MasterEarningOrderItem(BaseModel):
    id: int
    category: str
    category_name: str = ""
    agreed_price: int
    commission_amount: int
    net: int
    net_amount: int


class MasterEarningsOut(BaseModel):
    completed_count: int
    gross_total: int
    commission_total: int
    net_total: int
    orders: list[MasterEarningOrderItem] = []

