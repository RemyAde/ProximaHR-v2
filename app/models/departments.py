from pydantic import BaseModel
from datetime import datetime, timezone
from typing import Optional

UTC = timezone.utc

class Department(BaseModel):
    company_id: str
    name: str
    hod: Optional[str] = None
    staffs: Optional[list] = [] #list of employee_ids
    staff_size: Optional[int] = 0
    created_at: datetime = datetime.now(UTC)
