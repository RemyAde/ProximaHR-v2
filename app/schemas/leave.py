from datetime import date
from pydantic import BaseModel, Field
from typing import Optional, Dict, List


class CreateLeave(BaseModel):
    leave_type: str
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    aditional_notes: Optional[str] = None

class LeavesCount(BaseModel):
    leave_count: int
    pending_leave_count: int
    approved_leave_count: int
    rejected_leave_count: int
    

class LeaveList(BaseModel):
    leave_data: List[dict] = Field(
        ...,
        description="list of dictionaries"
    )
    class Config:
        json_schema_extra = {
            "example": {
                "leave_data": [
                    {
                        "leave_id": "12345",
                        "leave_type": "sick",
                        "duration": 3,
                        "start_date": "2023-10-01",
                        "end_date": "2023-10-03",
                        "status": "approved",
                        "employee_details": {
                            "name": "John Doe",
                            "department": "HR"
                        }
                    }
                ]
            }
        }

class LeaveTypeSummary(BaseModel):
    leave_type_counts: Dict[str, int]
    year: int

