from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt

from app.core.config import MAX_DB_INT
from app.models.enums import (
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
    Role,
    SelectionMode,
)
from app.schemas.order import HistoryOut, OfferOut
from app.schemas.quote import QuoteOut


class AdminOrderListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: OrderStatus
    category: str
    category_name: str
    category_id: int
    customer_id: int
    customer_name: str
    customer_phone: str
    master_id: int | None = None
    master_name: str | None = None
    city: str
    district: str
    agreed_price: int | None = None
    commission_amount: int | None = None
    created_at: datetime


class AdminPaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int
    method: PaymentMethod
    amount: int
    status: PaymentStatus
    created_at: datetime


class AdminReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int
    rating: int
    comment: str | None = None
    created_at: datetime


class AdminOrderDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: OrderStatus
    category_id: int
    category: str
    category_name: str
    customer_id: int
    customer_name: str
    customer_phone: str
    master_id: int | None = None
    master_name: str | None = None
    city: str
    district: str
    address: str
    description: str
    selection_mode: SelectionMode
    agreed_price: int | None = None
    commission_rate: int
    commission_amount: int | None = None
    created_at: datetime
    history: list[HistoryOut] = []
    offers: list[OfferOut] = []
    quotes: list[QuoteOut] = []
    payment: AdminPaymentOut | None = None
    review: AdminReviewOut | None = None


class AdminUserItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    phone: str
    full_name: str
    role: Role
    is_active: bool
    created_at: datetime
    profile_id: int | None = None
    is_approved: bool | None = None
    is_available: bool | None = None
    rating_avg: float | None = None
    rating_count: int | None = None


class UserStatusIn(BaseModel):
    is_active: StrictBool


class AdminAssignIn(BaseModel):
    master_id: StrictInt = Field(le=MAX_DB_INT)


class CommissionOrderItem(BaseModel):
    id: int
    completed_at: datetime | None = None
    category_name: str
    master_name: str
    agreed_price: int
    commission_rate: int
    commission_amount: int
    master_net: int
    payment_amount: int | None = None
    payment_status: str | None = None


class CommissionsReportOut(BaseModel):
    total_completed_orders: int
    total_orders: int
    total: int
    gross_total: int
    commission_total: int
    orders: list[CommissionOrderItem]
