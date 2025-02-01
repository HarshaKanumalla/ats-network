#backend/app/models/user.py

"""User-related data models and validation schemas."""
from typing import Optional, List
from pydantic import EmailStr, Field, field_validator
import re
from datetime import datetime

from .common import AuditedModel, PyObjectId
from ..core.constants import UserRole, UserStatus

class UserBase(AuditedModel):
    """Base user model with common fields."""
    
    email: EmailStr = Field(..., description="User's email address")
    full_name: str = Field(..., min_length=2, max_length=100)
    role: UserRole = Field(default=UserRole.ATS_TESTING)
    status: UserStatus = Field(default=UserStatus.PENDING)
    is_active: bool = Field(default=True)
    is_verified: bool = Field(default=False)
    center_id: Optional[PyObjectId] = None
    
    # ATS Center details
    ats_address: str = Field(..., min_length=5, max_length=200)
    city: str = Field(..., min_length=2, max_length=100)
    district: str = Field(..., min_length=2, max_length=100)
    state: str = Field(..., min_length=2, max_length=100)
    pin_code: str = Field(..., pattern=r'^\d{6}$')
    
    # Document references
    documents: List[str] = Field(default_factory=list)
    profile_photo: Optional[str] = None

class UserCreate(UserBase):
    """Model for user registration."""
    
    password: str = Field(..., min_length=8, max_length=100)
    confirm_password: str = Field(..., min_length=8, max_length=100)
    
    @field_validator('password')
    def validate_password(cls, v):
        """Validate password strength."""
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not re.search(r'\d', v):
            raise ValueError('Password must contain at least one number')
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', v):
            raise ValueError('Password must contain at least one special character')
        return v
    
    @field_validator('confirm_password')
    def passwords_match(cls, v, values):
        """Validate password confirmation."""
        if 'password' in values.data and v != values.data['password']:
            raise ValueError('Passwords do not match')
        return v

class UserUpdate(UserBase):
    """Model for updating user information."""
    
    full_name: Optional[str] = None
    ats_address: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    state: Optional[str] = None
    pin_code: Optional[str] = None
    profile_photo: Optional[str] = None

class UserInDB(UserBase):
    """Internal user model with hashed password."""
    
    hashed_password: str
    verification_token: Optional[str] = None
    reset_token: Optional[str] = None
    reset_token_expires: Optional[datetime] = None
    last_login: Optional[datetime] = None
    
    # For RTO officers
    jurisdiction_centers: List[PyObjectId] = Field(default_factory=list)
    
    class Config:
        """Model configuration."""
        json_encoders = {
            datetime: lambda dt: dt.isoformat() if dt else None
        }

class UserResponse(UserBase):
    """User information response model."""
    
    id: PyObjectId = Field(..., alias="_id")
    
    class Config:
        """Response model configuration."""
        json_encoders = {
            PyObjectId: str
        }
        
    def dict(self, *args, **kwargs):
        """Customize dictionary representation."""
        d = super().dict(*args, **kwargs)
        # Remove sensitive fields
        d.pop('hashed_password', None)
        d.pop('verification_token', None)
        d.pop('reset_token', None)
        d.pop('reset_token_expires', None)
        return d

class AdminUserUpdate(UserBase):
    """Model for admin-level user updates."""
    
    status: Optional[UserStatus] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    center_id: Optional[PyObjectId] = None
    jurisdiction_centers: Optional[List[PyObjectId]] = None
    
    rejection_reason: Optional[str] = Field(None, min_length=10, max_length=500)
    approval_notes: Optional[str] = Field(None, max_length=500)