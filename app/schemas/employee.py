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
    working_hours: Optional[int] = 0
    weekly_workdays: Optional[int] = 0
    base_salary: Optional[int] = None
    payment_frequency: Optional[str] = None
    account_name: Optional[str] = None
    account_number: Optional[str] = None
    bank_name: Optional[str] = None
    overtime_hours_allowance: Optional[int] = 0
    housing_allowance: Optional[int] = 0
    transport_allowance: Optional[int] = 0
    medical_allowance: Optional[int] = 0
    employee_contribution: Optional[float] = 0.0
    company_match: Optional[float] = 0.0
    paye_deduction: Optional[float] = 0.0
    insurance_provider: Optional[str] = None
    leadway_insurance: Optional[str] = None
    annual_leave_days: Optional[int] = 0


class EditEmployee(BaseModel):
   
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
   working_hours: Optional[int] = 0
   weekly_workdays: Optional[int] = 0
   base_salary: Optional[int] = None
   payment_frequency: Optional[str] = None
   account_name: Optional[str] = None
   account_number: Optional[str] = None
   bank_name: Optional[str] = None
   overtime_hours_allowance: Optional[int] = 0
   housing_allowance: Optional[int] = 0
   transport_allowance: Optional[int] = 0
   medical_allowance: Optional[int] = 0
   employee_contribution: Optional[float] = 0.0
   company_match: Optional[float] = 0.0
   paye_deduction: Optional[float] = 0.0
   insurance_provider: Optional[str] = None
   leadway_insurance: Optional[str] = None
   annual_leave_days: Optional[int] = 0