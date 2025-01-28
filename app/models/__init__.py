"""Data models module initialization."""
from .user import (
    User,
    UserBase,
    UserCreate,
    UserInDB,
    UserUpdate,
    UserResponse,
    AdminUserUpdate,
    TokenData,
    Token,
    Role,
    UserStatus
)
from .location import (
    Location,
    LocationBase,
    LocationCreate,
    LocationResponse
)

__all__ = [
    # User models
    'User',
    'UserBase',
    'UserCreate',
    'UserInDB',
    'UserUpdate',
    'UserResponse',
    'AdminUserUpdate',
    'TokenData',
    'Token',
    'Role',
    'UserStatus',
    # Location models
    'Location',
    'LocationBase',
    'LocationCreate',
    'LocationResponse'
]