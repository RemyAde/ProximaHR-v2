from pydantic import BaseModel, EmailStr


class Company(BaseModel):
    registration_number: str
    name: str
    email: EmailStr
    industry: str
    