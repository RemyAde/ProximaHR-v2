from typing import Optional, List
from pydantic import BaseModel, Field


class DepartmentCreate(BaseModel):
    name: str = Field(..., description="Name of the department.")
    hod: Optional[str] = Field(
        None, 
        description="The employee ID of the Head of Department (HOD)."
    )
    staffs: Optional[List[str]] = Field(
        default_factory=list, 
        description="List of employee IDs representing the staff members in the department."
    )
    description: Optional[str] = Field(
        None, 
        description="A brief description of the department."
    )