from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)

    @field_validator("body")
    @classmethod
    def _body(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Xabar bo'sh bo'lmasligi kerak")
        return v


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int
    sender_id: int
    sender_name: str = ""
    body: str
    created_at: datetime
