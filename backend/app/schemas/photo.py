from datetime import datetime

from pydantic import BaseModel


class PhotoOut(BaseModel):
    id: int
    url: str
    created_at: datetime
