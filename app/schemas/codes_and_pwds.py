from pydantic import BaseModel, Field, field_validator
import re


class Code(BaseModel):
    code: int


class PasswordReset(BaseModel):
    new_password: str = Field(..., 
                              min_length=8, 
                              max_length=100,
                              description="Password must contain at least one lowercase, one uppercase letter, and a number")
    confirm_password: str

    @field_validator("new_password")
    def validate_password(cls, new_password):
        # Manual regex checks for uppercase, lowercase, and digits
        if not re.search(r"[a-z]", new_password):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"[A-Z]", new_password):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"\d", new_password):
            raise ValueError("Password must contain at least one number")
        return new_password

    @field_validator("confirm_password")
    def passwords_match(cls, confirm_password, info):
        if "new_password" in info.data and confirm_password != info.data["new_password"]:
            raise ValueError("Passwords do not match")
        return confirm_password