from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, StrictInt


class ReviewCreate(BaseModel):
    rating: StrictInt = Field(..., ge=1, le=5)
    comment: str | None = Field(default=None, max_length=1000)


class ReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rating: int
    comment: str | None = None
    created_at: datetime


class MasterReviewItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rating: int
    comment: str | None = None
    created_at: datetime
    customer_first_name: str


class MasterReviewsOut(BaseModel):
    rating_avg: float
    rating_count: int
    reviews: list[MasterReviewItem]
    items: list[MasterReviewItem] = []


class OrderReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rating: int
    comment: str | None = None
    created_at: datetime | None = None
