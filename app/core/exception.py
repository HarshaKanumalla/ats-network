# backend/app/core/exceptions.py

from typing import Optional
from fastapi import status

class CustomException(Exception):
    """Base exception class for custom exceptions."""
    
    def __init__(
        self,
        detail: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        error_code: Optional[str] = None
    ):
        self.detail = detail
        self.status_code = status_code
        self.error_code = error_code or str(status_code)

class AuthenticationError(CustomException):
    """Exception for authentication failures."""
    
    def __init__(self, detail: str = "Authentication failed"):
        super().__init__(
            detail=detail,
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code="AUTH_ERROR"
        )

class AuthorizationError(CustomException):
    """Exception for authorization failures."""
    
    def __init__(self, detail: str = "Insufficient permissions"):
        super().__init__(
            detail=detail,
            status_code=status.HTTP_403_FORBIDDEN,
            error_code="FORBIDDEN"
        )

class DatabaseError(CustomException):
    """Exception for database operation failures."""
    
    def __init__(self, detail: str = "Database operation failed"):
        super().__init__(
            detail=detail,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_code="DB_ERROR"
        )

class ValidationError(CustomException):
    """Exception for data validation failures."""
    
    def __init__(self, detail: str = "Validation failed"):
        super().__init__(
            detail=detail,
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="VALIDATION_ERROR"
        )

# backend/app/api/v1/router.py

from fastapi import APIRouter
from app.api.v1.endpoints import (
    auth,
    users,
    centers,
    tests,
    vehicles,
    admin,
    monitoring
)

# Create main API router
api_router = APIRouter()

# Include all endpoint routers
api_router.include_router(
    auth.router,
    prefix="/auth",
    tags=["Authentication"]
)

api_router.include_router(
    users.router,
    prefix="/users",
    tags=["Users"]
)

api_router.include_router(
    centers.router,
    prefix="/centers",
    tags=["Centers"]
)

api_router.include_router(
    tests.router,
    prefix="/tests",
    tags=["Tests"]
)

api_router.include_router(
    vehicles.router,
    prefix="/vehicles",
    tags=["Vehicles"]
)

api_router.include_router(
    admin.router,
    prefix="/admin",
    tags=["Administration"]
)

api_router.include_router(
    monitoring.router,
    prefix="/monitoring",
    tags=["Monitoring"]
)
