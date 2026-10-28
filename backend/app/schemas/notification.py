from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    title: str
    body: str
    related_order_id: Optional[int]
    is_read: bool
    created_at: datetime


class UnreadCountOut(BaseModel):
    unread_count: int
