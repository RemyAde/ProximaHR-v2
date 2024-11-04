from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone

UTC = timezone.utc


class RandomCodes(BaseModel):
    user_email: str
    code: int
    expiration_time: datetime
    verified: bool = False
    created_at: datetime = datetime.now(UTC)
    updated_at: datetime