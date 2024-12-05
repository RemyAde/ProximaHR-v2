from pydantic import BaseModel
from typing import Optional
from datetime import date

class CreateEmployeeCredentials(BaseModel):
    employee_id: str


class CreateEmployee(BaseModel):
    employee_id: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone_number: Optional[str] = None
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    home_address: Optional[str] = None
    country: Optional[str] = None
    job_title: Optional[str] = None
    department: Optional[str] = None
    role: Optional[str] = None
    employment_date: Optional[date] = None
    work_mode: Optional[str] = None
    work_location: Optional[str] = None
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


class EditEmployee(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    home_address: Optional[str] = None
    phone_number: Optional[str] = None
    email: Optional[str] = None
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    country: Optional[str] = None
    job_title: Optional[str] = None
    department: Optional[str] = None
    role: Optional[str] = None
    work_location: Optional[str] = None
    employment_date: Optional[date] = None
    salary: Optional[int] = None
    payment_frequency: Optional[str] = None
    bonus_eligibility: Optional[str] = None
    pension_plan: Optional[str] = None
    health_insurance: Optional[str] = None
    leave_days: Optional[int] = None