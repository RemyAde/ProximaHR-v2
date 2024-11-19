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
    home_address: Optional[str] = None
    phone_number: Optional[str] = None
    password: str
    email: Optional[str] = None
    date_of_birth: Optional[datetime] = None
    gender: Optional[str] = None
    country: Optional[str] = None
    job_title: Optional[str] = None
    department: Optional[str] = None
    role: Optional[str] = None
    work_location = Optional[str] = None
    employment_date: Optional[datetime] = None
    salary: Optional[int] = None
    payment_frequency: Optional[str] = None
    bonus_eligibility: Optional[str] = None
    pension_plan: Optional[str] = None
    health_insurance: Optional[str] = None
    leave_days = Optional[int] = None
    profile_image: Optional[str] = None
    employment_status: str = "active" # or inactive or suspended
    date_created: datetime = datetime.now(UTC)