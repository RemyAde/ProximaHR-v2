from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List

class TimerLog(BaseModel):
    start_time: datetime
    end_time: Optional[datetime] = None
    paused_time: Optional[List[datetime]] = None  # List of pause/resume timestamps

class Attendance(BaseModel):
    date: datetime
    hours_worked: float
    overtime_hours: float = 0.0
    attendance_status: str  # present, undertime, absen