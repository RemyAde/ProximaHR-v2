from typing import Optional
from pydantic import BaseModel


class DepartmentCreate(BaseModel):
    name: str
    hod: Optional[str] = None