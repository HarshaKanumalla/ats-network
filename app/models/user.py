"""User-related data models."""
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum
from pydantic import EmailStr, Field, field_validator, computed_field, model_validator

from ..models.base import BaseDBModel, PyObjectId

class Role(str, Enum):
    """User role enumeration."""
    ADMIN = "admin"
    USER = "user"

class UserStatus(str, Enum):
    """User status enumeration."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"

class UserBase(BaseDBModel):
    """Base model for user data."""
    
    email: EmailStr = Field(..., description="User's email address")
    full_name: str = Field(..., min_length=2, max_length=100)
    ats_address: str = Field(..., min_length=5, max_length=200)
    city: str = Field(..., min_length=2, max_length=100)
    district: str = Field(..., min_length=2, max_length=100)
    state: str = Field(..., min_length=2, max_length=100)
    pin_code: str = Field(..., pattern=r'^\d{6}$')
    status: UserStatus = Field(default=UserStatus.PENDING)
    role: Role = Field(default=Role.USER)

    model_config = {
        "json_schema_extra": {
            "example": {
                "email": "user@example.com",
                "full_name": "John Doe",
                "ats_address": "123 ATS Street",
                "city": "Visakhapatnam",
                "district": "Visakhapatnam",
                "state": "Andhra Pradesh",
                "pin_code": "530001"
            }
        }
    }

class UserCreate(UserBase):
    """Model for user creation."""
    
    password: str = Field(..., min_length=8, max_length=100)
    confirm_password: str = Field(..., min_length=8, max_length=100)

    @field_validator('confirm_password')
    def passwords_match(cls, v: str, info: Dict[str, Any]) -> str:
        """Validate that passwords match."""
        if 'password' in info.data and v != info.data['password']:
            raise ValueError('Passwords do not match')
        return v

    @field_validator('password')
    def password_strength(cls, v: str) -> str:
        """Validate password strength."""
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(c.islower() for c in v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain at least one number')
        if not any(c in '!@#$%^&*()' for c in v):
            raise ValueError('Password must contain at least one special character')
        return v

class UserInDB(UserBase):
    """Internal user model with database fields."""
    
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    hashed_password: str
    is_active: bool = True
    is_verified: bool = False
    last_login: Optional[datetime] = None
    documents: List[str] = []
    verification_token: Optional[str] = None
    reset_token: Optional[str] = None
    reset_token_expires: Optional[datetime] = None

    model_config = {
        "json_encoders": {
            PyObjectId: str
        },
        "populate_by_name": True
    }

    def dict(self, *args, **kwargs):
        """Override dict method to ensure ID is properly serialized."""
        d = super().dict(*args, **kwargs)
        d["id"] = str(d.get("_id", d.get("id", "")))
        return d

class User(BaseDBModel):
    """Public user model."""
    
    id: PyObjectId = Field(alias="_id")
    full_name: str
    email: EmailStr
    ats_address: str
    city: str
    district: str
    state: str
    pin_code: str
    role: Role
    status: UserStatus
    is_verified: bool
    is_active: bool
    documents: List[str] = []

class Token(BaseDBModel):
    """Authentication token model."""
    
    access_token: str
    token_type: str = "bearer"
    user: User

    model_config = {
        "json_schema_extra": {
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
                "user": {
                    "id": "507f1f77bcf86cd799439011",
                    "email": "user@example.com",
                    "role": "user"
                }
            }
        }
    }

class TokenData(BaseDBModel):
    """Token payload data model."""
    
    user_id: str
    email: EmailStr
    role: Role
    exp: datetime

class UserUpdate(BaseDBModel):
    """Model for user information updates."""
    
    full_name: Optional[str] = None
    ats_address: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    state: Optional[str] = None
    pin_code: Optional[str] = None
    status: Optional[UserStatus] = None

    @field_validator('pin_code')
    def validate_pin_code(cls, v: Optional[str]) -> Optional[str]:
        """Validate pin code format if provided."""
        if v and not v.isdigit() and len(v) != 6:
            raise ValueError('Invalid PIN code format')
        return v

class UserResponse(BaseDBModel):
    """Model for user operation responses."""
    
    status: str
    message: str
    data: Optional[User] = None

class AdminUserUpdate(BaseDBModel):
    """Model for admin-level user updates."""
    
    status: Optional[UserStatus] = None
    is_active: Optional[bool] = None
    role: Optional[Role] = None
    rejection_reason: Optional[str] = Field(None, min_length=10, max_length=500)