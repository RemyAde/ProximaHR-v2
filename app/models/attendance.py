from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List

class TimerLog(BaseModel):
    company_id: str
    employee_id: str
    start_time: datetime
    end_time: Optional[datetime] = None
    paused_intervals: List[dict] = Field(default_factory=list)  # e.g., [{"start": datetime, "end": datetime}]
    total_hours: Optional[float] = 0
    date: datetime  # To group logs by day