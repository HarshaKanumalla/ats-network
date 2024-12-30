from typing import Any, Optional, List, Dict, Annotated
from pydantic import BaseModel, EmailStr, Field, field_validator, ConfigDict, GetCoreSchemaHandler
from pydantic_core import core_schema
from datetime import datetime
from enum import Enum
from bson import ObjectId


class PyObjectId(str):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, value):
        if not isinstance(value, ObjectId):
            if not ObjectId.is_valid(value):
                raise ValueError("Invalid ObjectId")
            value = ObjectId(value)
        return str(value)

    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        _source_type: Any,
        _handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        return core_schema.json_or_python_schema(
            json_schema=core_schema.str_schema(),
            python_schema=core_schema.union_schema([
                core_schema.str_schema(),
                core_schema.is_instance_schema(ObjectId),
            ]),
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda x: str(x) if isinstance(x, ObjectId) else x,
                return_schema=core_schema.str_schema(),
            ),
        )


class Role(str, Enum):
    ADMIN = "admin"
    USER = "user"


class UserStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class UserBase(BaseModel):
    email: EmailStr
    full_name: str
    ats_address: str
    city: str
    district: str
    state: str
    pin_code: str
    status: UserStatus = UserStatus.PENDING
    role: Role = Role.USER

    model_config = ConfigDict(from_attributes=True)


class UserCreate(UserBase):
    password: str
    confirm_password: str

    @field_validator('confirm_password')
    def passwords_match(cls, v, info):
        if 'password' in info.data and v != info.data['password']:
            raise ValueError('Passwords do not match')
        return v

    model_config = ConfigDict(from_attributes=True)


class UserInDB(UserBase):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    hashed_password: str
    is_active: bool = True
    is_verified: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None
    last_login: Optional[datetime] = None
    documents: List[str] = []
    verification_token: Optional[str] = None
    reset_token: Optional[str] = None
    reset_token_expires: Optional[datetime] = None

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        arbitrary_types_allowed=True
    )


class User(BaseModel):
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
    created_at: datetime
    documents: List[str] = []

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        arbitrary_types_allowed=True
    )


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: User

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
                "user": {
                    "id": "507f1f77bcf86cd799439011",
                    "email": "john.doe@example.com",
                    "role": "user"
                }
            }
        }
    )


class TokenData(BaseModel):
    user_id: str
    email: EmailStr
    role: Role
    exp: datetime


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    ats_address: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    state: Optional[str] = None
    pin_code: Optional[str] = None
    status: Optional[UserStatus] = None

    model_config = ConfigDict(from_attributes=True)


class UserResponse(BaseModel):
    status: str
    message: str
    data: Optional[User] = None


class AdminUserUpdate(BaseModel):
    status: Optional[UserStatus] = None
    is_active: Optional[bool] = None
    role: Optional[Role] = None
    rejection_reason: Optional[str] = None

# Export all models
__all__ = [
    'PyObjectId',
    'Role',
    'UserStatus',
    'UserBase',
    'UserCreate',
    'UserUpdate',
    'UserInDB',
    'User',
    'Token',
    'TokenData',
    'UserResponse',
    'AdminUserUpdate'
]