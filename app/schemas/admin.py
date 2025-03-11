from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional
from datetime import datetime, date


class CreateAdmin(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    password: str
    admin_code: str


class EmailInput(BaseModel):
    email: EmailStr


class ExtendedAdmin(BaseModel):
    date_of_birth: Optional[date] = None  # Stored as BSON datetime in MongoDB (ISODate)
    gender: Optional[str] = None
    address: Optional[str] = None

    @field_validator('date_of_birth', mode='before')
    def convert_date_to_datetime(cls, v):
        if v is None:
            return v
        if isinstance(v, datetime):
            return v
        if isinstance(v, date):
            return datetime.combine(v, datetime.min.time())
        return v