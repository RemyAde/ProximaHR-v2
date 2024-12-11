from pydantic import BaseModel
from datetime import datetime, timezone
from typing import Optional

UTC = timezone.utc


class Admin(BaseModel):
    first_name: str
    last_name: str
    email: str
    password: str
    profile_image: Optional[str] = None
    company_id: str
    role: str = "admin"
    date_created: datetime = datetime.now(UTC)