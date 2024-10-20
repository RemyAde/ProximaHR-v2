from pydantic import BaseModel
from datetime import datetime, timezone
from typing import Optional

UTC = timezone.utc


class Employee(BaseModel):
    employee_id: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    password: str
    email: Optional[str] = None
    company_id: str
    department: Optional[str] = None
    date_created: datetime = datetime.now(UTC)