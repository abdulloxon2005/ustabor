from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator, model_validator

from app.core.config import MAX_DB_INT


class LocationUpdate(BaseModel):
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    sharing_enabled: StrictBool

    @model_validator(mode="after")
    def coordinates_required_when_sharing(self):
        if self.sharing_enabled and (self.latitude is None or self.longitude is None):
            raise ValueError("Joylashuv ruxsati yoqilganda koordinatalar kerak")
        return self


class NearbyMaster(BaseModel):
    id: int
    full_name: str
    city: str
    district: str
    rating_avg: float
    rating_count: int
    distance_km: float | None


class MasterLocationOut(BaseModel):
    master_id: int
    full_name: str
    latitude: float
    longitude: float
    location_updated_at: datetime | None
    is_available: bool


class DeviceTokenIn(BaseModel):
    token: str = Field(min_length=16, max_length=512)
    platform: Literal["android", "ios", "web"]
    is_active: StrictBool = True

    @field_validator("token")
    @classmethod
    def token_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Device token bo'sh bo'lmasligi kerak")
        return value


class DispatchStatusOut(BaseModel):
    order_id: int
    status: str
    dispatch_radius_km: int
    pending_offers: int
    rejected_offers: int
    expired_offers: int
    accepted_master_id: int | None = None
    message: str


class AdminMasterItem(BaseModel):
    id: int
    user_id: int
    full_name: str
    phone: str
    city: str
    district: str
    is_approved: bool
    is_available: bool
    rating_avg: float
    rating_count: int
    services: list[str]
    completed_orders: int
    rejected_offers: int
    gross_earnings: int


class AdminMasterStats(AdminMasterItem):
    location_sharing_enabled: bool
    location_updated_at: datetime | None


class CommissionSettingsOut(BaseModel):
    enabled: bool
    rate: int
    updated_at: datetime | None = None


class CommissionSettingsIn(BaseModel):
    enabled: StrictBool
    rate: StrictInt = Field(ge=0, le=100)


class ChatMessageModerationIn(BaseModel):
    message_id: StrictInt = Field(gt=0, le=MAX_DB_INT)
    hide: StrictBool
    note: str | None = Field(default=None, max_length=1000)


class ChatReportIn(BaseModel):
    reason: str = Field(min_length=5, max_length=1000)

    @field_validator("reason")
    @classmethod
    def clean_reason(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 5:
            raise ValueError("Shikoyat sababi kamida 5 ta belgidan iborat bo'lishi kerak")
        return value


class ChatReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int
    message_id: int
    reported_by: int
    reason: str
    status: str
    admin_note: str | None
    created_at: datetime
    reviewed_at: datetime | None
    message_body: str | None = None
    reporter_name: str | None = None


class AnalyticsFilter(BaseModel):
    start_date: date | None = None
    end_date: date | None = None
    category_id: int | None = Field(default=None, gt=0, le=MAX_DB_INT)
    master_id: int | None = Field(default=None, gt=0, le=MAX_DB_INT)
    region: str | None = Field(default=None, max_length=80)
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0, le=MAX_DB_INT)
