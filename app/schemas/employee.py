from pydantic import BaseModel
from typing import Optional


class CreateEmployee(BaseModel):
    employee_id: str