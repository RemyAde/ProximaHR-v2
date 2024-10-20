from pydantic import BaseModel
from datetime import datetime, timezone
from typing import Optional

UTC = timezone.utc


class Admin(BaseModel):
    first_name: str
    last_name: str
    email: str
    password: str
    company_id: str
    role: Optional[str] = None
    date_created: datetime = datetime.now(UTC)