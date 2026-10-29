from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, StrictInt


class ReviewCreate(BaseModel):
    rating: StrictInt = Field(..., ge=1, le=5)
    comment: str | None = Field(default=None, max_length=1000)
    # Ixtiyoriy, batafsil baholash
    quality_rating: StrictInt | None = Field(default=None, ge=1, le=5)
    timeliness_rating: StrictInt | None = Field(default=None, ge=1, le=5)
    price_rating: StrictInt | None = Field(default=None, ge=1, le=5)


class ReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rating: int
    comment: str | None = None
    quality_rating: int | None = None
    timeliness_rating: int | None = None
    price_rating: int | None = None
    created_at: datetime


class MasterReviewItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rating: int
    comment: str | None = None
    quality_rating: int | None = None
    timeliness_rating: int | None = None
    price_rating: int | None = None
    created_at: datetime
    customer_first_name: str


class MasterReviewsOut(BaseModel):
    rating_avg: float
    rating_count: int
    # Ixtiyoriy sub-reytinglar o'rtachasi (faqat shu qiymat berilgan sharhlar bo'yicha)
    quality_avg: float | None = None
    timeliness_avg: float | None = None
    price_avg: float | None = None
    reviews: list[MasterReviewItem]
    items: list[MasterReviewItem] = []


class OrderReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rating: int
    comment: str | None = None
    quality_rating: int | None = None
    timeliness_rating: int | None = None
    price_rating: int | None = None
    created_at: datetime | None = None
