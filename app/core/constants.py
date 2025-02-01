#backend/app/core/exceptions.py

"""Custom exceptions for the application."""
from typing import Optional, Any, Dict
from fastapi import status

class APIException(Exception):
    """Base exception for API errors."""
    
    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        data: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.status_code = status_code
        self.data = data or {}
        super().__init__(self.message)

class AuthenticationError(APIException):
    """Exception for authentication failures."""
    
    def __init__(
        self,
        message: str = "Authentication failed",
        data: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED,
            data=data
        )

class AuthorizationError(APIException):
    """Exception for authorization failures."""
    
    def __init__(
        self,
        message: str = "Insufficient permissions",
        data: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
            data=data
        )

class ValidationError(APIException):
    """Exception for data validation failures."""
    
    def __init__(
        self,
        message: str = "Validation failed",
        data: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
            data=data
        )

class NotFoundError(APIException):
    """Exception for resource not found errors."""
    
    def __init__(
        self,
        message: str = "Resource not found",
        data: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            status_code=status.HTTP_404_NOT_FOUND,
            data=data
        )

class DuplicateError(APIException):
    """Exception for duplicate resource errors."""
    
    def __init__(
        self,
        message: str = "Resource already exists",
        data: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            status_code=status.HTTP_409_CONFLICT,
            data=data
        )

class FileUploadError(APIException):
    """Exception for file upload failures."""
    
    def __init__(
        self,
        message: str = "File upload failed",
        data: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
            data=data
        )

class DatabaseError(APIException):
    """Exception for database operation failures."""
    
    def __init__(
        self,
        message: str = "Database operation failed",
        data: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            data=data
        )

class ExternalServiceError(APIException):
    """Exception for external service failures."""
    
    def __init__(
        self,
        message: str = "External service error",
        data: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            status_code=status.HTTP_502_BAD_GATEWAY,
            data=data
        )