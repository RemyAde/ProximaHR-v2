from datetime import date
from pydantic import BaseModel
from typing import Optional


class CreateLeave(BaseModel):
    leave_type: str
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    aditional_notes: Optional[str] = None