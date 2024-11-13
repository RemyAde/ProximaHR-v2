from pydantic import BaseModel
from datetime import datetime, timezone
from typing import Optional
from datetime import date

UTC = timezone.utc


class Employee(BaseModel):
    company_id: str
    employee_id: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    password: str
    email: Optional[str] = None
    dob: Optional[datetime] = None
    job_title: Optional[str] = None
    department: Optional[str] = None
    employment_status: Optional[str] = None
    hire_date: Optional[datetime] = None
    contract_type: Optional[str] = None
    duration: Optional[str] = None
    salary: Optional[int] = None
    profile_image: Optional[str] = None
    date_created: datetime = datetime.now(UTC)