# backend/app/core/schemas/responses.py

from typing import Optional, Any, Generic, TypeVar
from pydantic import BaseModel
from datetime import datetime
from enum import Enum

T = TypeVar('T')

class ResponseStatus(str, Enum):
    """Enum for response status."""
    SUCCESS = "success"
    ERROR = "error"

class ErrorCodes(str, Enum):
    """Enum for error codes."""
    VALIDATION_ERROR = "VALIDATION_ERROR"
    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
    AUTHORIZATION_ERROR = "AUTHORIZATION_ERROR"
    DATABASE_ERROR = "DATABASE_ERROR"
    BUSINESS_LOGIC_ERROR = "BUSINESS_LOGIC_ERROR"
    FILE_OPERATION_ERROR = "FILE_OPERATION_ERROR"
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
    INTERNAL_SERVER_ERROR = "INTERNAL_SERVER_ERROR"

class BaseResponse(BaseModel, Generic[T]):
    """
    A generic base response model for successful API responses.

    Attributes:
        status (ResponseStatus): The status of the response (e.g., "success").
        message (str): A descriptive message about the response.
        timestamp (datetime): The time the response was generated.
        data (Optional[T]): The data payload of the response.
        meta (Optional[dict]): Additional metadata (e.g., pagination info).
    """
    status: ResponseStatus
    message: str
    timestamp: datetime = datetime.utcnow
    data: Optional[T] = None
    meta: Optional[dict] = None

class ErrorResponse(BaseModel):
    """
    A model for error responses.

    Attributes:
        status (ResponseStatus): The status of the response (always "error").
        message (str): A descriptive message about the error.
        error_code (ErrorCodes): A standardized error code.
        timestamp (datetime): The time the error occurred.
        details (Optional[dict]): Additional details about the error.
        path (Optional[str]): The request path where the error occurred.
    """
    status: ResponseStatus = ResponseStatus.ERROR
    message: str
    error_code: ErrorCodes
    timestamp: datetime = datetime.utcnow
    details: Optional[dict] = None
    path: Optional[str] = None