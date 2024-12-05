from pydantic import BaseModel
from datetime import datetime, timezone
from typing import Optional, Dict
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
    employment_date: Optional[datetime] = None
    base_salary: Optional[int] = None
    payment_frequency: Optional[str] = None
    overtime_hours_allowance: Optional[int] = 0
    housing_allowance: Optional[int] = 0
    transport_allowance: Optional[int] = 0
    medical_allowance: Optional[int] = 0
    health_insurance: Optional[str] = None
    employee_pension_plan_percentage: Optional[int] = 0
    employer_pension_plan_percentage: Optional[int] = 0
    tax_deductions: Optional[int] = 0
    retirement_fund: Optional[int] = 0
    annual_leave_days: Optional[int] = 0
    used_leave_days: Optional[int] = 0
    carried_over_days: Optional[int] = 0
    current_year: str = current_year
    position: str = "member"
    employment_status: str = "active" # or inactive or suspended
    # suspension: Optional[Dict] = {}
    date_created: datetime = current_datetime