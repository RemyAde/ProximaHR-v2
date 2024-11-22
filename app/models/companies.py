from pydantic import BaseModel
from datetime import datetime, timezone
from typing import Optional, List 

UTC = timezone.utc

class Company(BaseModel):
    registration_number: str
    name: str
    industry: str
    email: str
    country: Optional[str] = None
    state: Optional[str] = None
    town: Optional[str] = None
    year_founded: Optional[int] = None
    staff_size: Optional[int] = 0
    departments: Optional[list] = None
    payment_type: Optional[str] = None
    subscription_start: Optional[datetime] = None
    subscription_end: Optional[datetime] = None
    company_url: Optional[str] = None
    admins: List[str] = []
    admin_creation_code: Optional[str] = None
    date_created: datetime = datetime.now(UTC)
