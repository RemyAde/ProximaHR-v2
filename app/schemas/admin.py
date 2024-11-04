from pydantic import BaseModel, EmailStr
from typing import Optional


class CreateAdmin(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    password: str
    role: Optional[str] = None


class EmailInput(BaseModel):
    email: EmailStr