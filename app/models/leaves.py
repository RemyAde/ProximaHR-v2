from datetime import datetime, timezone
from pydantic import BaseModel
from typing import Optional

UTC = timezone.utc


class Leave(BaseModel):
    company_id: str
    employee_id: str
    leave_type: str
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    duration: Optional[int] = 0 # no of days
    additional_notes: Optional[str] = None
    status: str = "pending" # or approved/rejected
    created_at: datetime = datetime.now(UTC)

