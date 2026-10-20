from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

from app.core.config import settings
from app.models.enums import QuoteStatus


class QuoteIn(BaseModel):
    price: StrictInt = Field(gt=0, le=settings.QUOTE_MAX_PRICE)
    note: str | None = Field(default=None, max_length=500)

    @field_validator("note")
    @classmethod
    def _note(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip()
            if not v:
                return None
        return v


class QuoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int
    master_id: int
    price: int
    note: str | None = None
    status: QuoteStatus
    created_at: datetime
