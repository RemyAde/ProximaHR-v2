from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import Optional, Dict, List
from datetime import date

UTC = timezone.utc
current_datetime = datetime.now(UTC)
current_year = current_datetime.year


class Employee(BaseModel):
    company_id: str
    employee_id: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    home_address: Optional[str] = None
    phone_number: Optional[str] = None
    password: str
    email: Optional[str] = None
    profile_image: Optional[str] = None
    date_of_birth: Optional[datetime] = None
    gender: Optional[str] = None
    country: Optional[str] = None
    job_title: Optional[str] = None
    department: Optional[str] = None
    role: Optional[str] = None
    work_mode: Optional[str] = None
    work_location: Optional[str] = None
    working_hours: int
    weekly_workdays: Optional[int] = 0 # number of working days per week
    monthly_overtime_hours: float = 0
    monthly_working_hours: float = 0
    attendance: List[dict] = Field(default_factory=list)  # [{"date": datetime, "hours_worked": float, "attendance_status": str}]
    employment_date: Optional[datetime] = None
    base_salary: Optional[int] = None
    payment_frequency: Optional[str] = None
    account_name: Optional[str] = None
    account_number: Optional[str] = None
    bank_name: Optional[str] = None
    payment_status: Optional[str] = "unpaid"
    overtime_hours_allowance: Optional[int] = 0
    housing_allowance: Optional[int] = 0
    transport_allowance: Optional[int] = 0
    medical_allowance: Optional[int] = 0
    employee_contribution: Optional[float] = 0.0
    company_match: Optional[float] = 0.0
    paye_deduction: Optional[float] = 0.0
    net_pay: Optional[float] = 0.0
    insurance_provider: Optional[str] = None
    leadway_insurance: Optional[str] = None
    annual_leave_days: Optional[int] = 0
    used_leave_days: Optional[int] = 0
    carried_over_days: Optional[int] = 0
    current_year: str = current_year
    position: str = "member"
    employment_status: str = "active" # or inactive or suspended
    date_created: datetime = current_datetime