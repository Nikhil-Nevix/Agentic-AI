"""
Authentication schemas.
"""

from datetime import datetime
import re
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, field_validator


PASSWORD_POLICY = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z\d]).{8,128}$")


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    full_name: Optional[str] = Field(default=None, max_length=255)
    role: str = Field(default="Service Desk User", max_length=100)

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        if not PASSWORD_POLICY.match(value):
            raise ValueError(
                "Password must include at least one uppercase letter, one lowercase letter, one number, and one symbol."
            )
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)


class AuthUserResponse(BaseModel):
    email: EmailStr
    role: str
    full_name: Optional[str] = None


class AuthResponse(BaseModel):
    user: AuthUserResponse
    message: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
