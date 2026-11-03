from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import DisputeStatus


class DisputeCreate(BaseModel):
    order_id: int | None = None
    reason: str = Field(min_length=5, max_length=1000)

    @field_validator("reason")
    @classmethod
    def _reason(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 5:
            raise ValueError("Sabab kamida 5 ta belgidan iborat bo'lishi kerak")
        return v


class DisputeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int | None = None
    status: DisputeStatus
    reason: str
    admin_note: str | None = None
    created_at: datetime
    resolved_at: datetime | None = None


class UserDisputeListItem(BaseModel):
    id: int
    order_id: int | None = None
    category_name: str
    order_status: str | None = None
    status: DisputeStatus
    reason: str
    admin_note: str | None = None
    created_at: datetime
    resolved_at: datetime | None = None


class AdminDisputeListItem(BaseModel):
    id: int
    order_id: int | None = None
    status: DisputeStatus
    reason: str
    admin_note: str | None = None
    raised_by_name: str
    raised_by_phone: str | None = None
    raised_by_role: str
    category_name: str
    order_status: str
    created_at: datetime
    resolved_at: datetime | None = None


class AdminDisputeResolve(BaseModel):
    status: Literal["resolved", "rejected"]
    admin_note: str | None = Field(default=None, max_length=1000)
