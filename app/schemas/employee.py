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
    dob: Optional[date] = None
    job_title: Optional[str] = None
    department: Optional[str] = None
    employment_status: Optional[str] = None
    hire_date: Optional[date] = None
    contract_type: Optional[str] = None
    duration: Optional[str] = None
    salary: Optional[int] = None