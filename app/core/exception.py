# backend/app/core/exception.py

from typing import Optional, Dict, Any
from fastapi import HTTPException, status
from datetime import datetime


class BaseATSException(Exception):
    """Base exception class for ATS Network application."""
    
    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    ):
        """Initialize base exception.
        
        Args:
            message: Error message
            error_code: Optional error code for tracking
            details: Additional error details
            status_code: HTTP status code
        """
        super().__init__(message)
        self.message = message
        self.error_code = error_code or "INTERNAL_ERROR"
        self.details = details or {}
        self.status_code = status_code
        self.timestamp = datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary format."""
        return {
            "error_code": self.error_code,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp.isoformat()
        }


class ValidationError(BaseATSException):
    """Exception for data validation errors."""
    
    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """Initialize validation error.
        
        Args:
            message: Error message
            field: Field that failed validation
            details: Additional error details
        """
        error_details = details or {}
        if field:
            error_details["field"] = field
            
        super().__init__(
            message=message,
            error_code="VALIDATION_ERROR",
            details=error_details,
            status_code=status.HTTP_400_BAD_REQUEST
        )


class AuthenticationError(BaseATSException):
    """Exception for authentication failures."""
    
    def __init__(
        self,
        message: str,
        details: Optional[Dict[str, Any]] = None
    ):
        """Initialize authentication error.
        
        Args:
            message: Error message
            details: Additional error details
        """
        super().__init__(
            message=message,
            error_code="AUTHENTICATION_ERROR",
            details=details,
            status_code=status.HTTP_401_UNAUTHORIZED
        )


class AuthorizationError(BaseATSException):
    """Exception for authorization failures."""
    
    def __init__(
        self,
        message: str,
        required_permission: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """Initialize authorization error.
        
        Args:
            message: Error message
            required_permission: Permission that was required
            details: Additional error details
        """
        error_details = details or {}
        if required_permission:
            error_details["required_permission"] = required_permission
            
        super().__init__(
            message=message,
            error_code="AUTHORIZATION_ERROR",
            details=error_details,
            status_code=status.HTTP_403_FORBIDDEN
        )


class DatabaseError(BaseATSException):
    """Exception for database operation failures."""
    
    def __init__(
        self,
        message: str,
        operation: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """Initialize database error.
        
        Args:
            message: Error message
            operation: Database operation that failed
            details: Additional error details
        """
        error_details = details or {}
        if operation:
            error_details["operation"] = operation
            
        super().__init__(
            message=message,
            error_code="DATABASE_ERROR",
            details=error_details,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


class TestError(BaseATSException):
    """Exception for test operation failures."""
    
    def __init__(
        self,
        message: str,
        test_type: Optional[str] = None,
        session_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """Initialize test error.
        
        Args:
            message: Error message
            test_type: Type of test that failed
            session_id: Test session identifier
            details: Additional error details
        """
        error_details = details or {}
        if test_type:
            error_details["test_type"] = test_type
        if session_id:
            error_details["session_id"] = session_id
            
        super().__init__(
            message=message,
            error_code="TEST_ERROR",
            details=error_details,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


class CenterError(BaseATSException):
    """Exception for ATS center operation failures."""
    
    def __init__(
        self,
        message: str,
        center_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """Initialize center error.
        
        Args:
            message: Error message
            center_id: Center identifier
            details: Additional error details
        """
        error_details = details or {}
        if center_id:
            error_details["center_id"] = center_id
            
        super().__init__(
            message=message,
            error_code="CENTER_ERROR",
            details=error_details,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


class VehicleError(BaseATSException):
    """Exception for vehicle operation failures."""
    
    def __init__(
        self,
        message: str,
        vehicle_number: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """Initialize vehicle error.
        
        Args:
            message: Error message
            vehicle_number: Vehicle registration number
            details: Additional error details
        """
        error_details = details or {}
        if vehicle_number:
            error_details["vehicle_number"] = vehicle_number
            
        super().__init__(
            message=message,
            error_code="VEHICLE_ERROR",
            details=error_details,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


class FileOperationError(BaseATSException):
    """Exception for file operation failures."""
    
    def __init__(
        self,
        message: str,
        file_type: Optional[str] = None,
        operation: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """Initialize file operation error.
        
        Args:
            message: Error message
            file_type: Type of file involved
            operation: Operation that failed
            details: Additional error details
        """
        error_details = details or {}
        if file_type:
            error_details["file_type"] = file_type
        if operation:
            error_details["operation"] = operation
            
        super().__init__(
            message=message,
            error_code="FILE_OPERATION_ERROR",
            details=error_details,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


class EmailError(BaseATSException):
    """Exception for email operation failures."""
    
    def __init__(
        self,
        message: str,
        email_type: Optional[str] = None,
        recipient: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """Initialize email error.
        
        Args:
            message: Error message
            email_type: Type of email
            recipient: Email recipient
            details: Additional error details
        """
        error_details = details or {}
        if email_type:
            error_details["email_type"] = email_type
        if recipient:
            error_details["recipient"] = recipient
            
        super().__init__(
            message=message,
            error_code="EMAIL_ERROR",
            details=error_details,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


class ReportError(BaseATSException):
    """Exception for report generation failures."""
    
    def __init__(
        self,
        message: str,
        report_type: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """Initialize report error.
        
        Args:
            message: Error message
            report_type: Type of report
            details: Additional error details
        """
        error_details = details or {}
        if report_type:
            error_details["report_type"] = report_type
            
        super().__init__(
            message=message,
            error_code="REPORT_ERROR",
            details=error_details,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


class ConfigurationError(BaseATSException):
    """Exception for configuration-related errors."""
    
    def __init__(
        self,
        message: str,
        config_key: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """Initialize configuration error.
        
        Args:
            message: Error message
            config_key: Configuration key that caused the error
            details: Additional error details
        """
        error_details = details or {}
        if config_key:
            error_details["config_key"] = config_key
            
        super().__init__(
            message=message,
            error_code="CONFIGURATION_ERROR",
            details=error_details,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


class ExternalServiceError(BaseATSException):
    """Exception for external service integration failures."""
    
    def __init__(
        self,
        message: str,
        service_name: str,
        details: Optional[Dict[str, Any]] = None
    ):
        """Initialize external service error.
        
        Args:
            message: Error message
            service_name: Name of external service
            details: Additional error details
        """
        error_details = details or {}
        error_details["service_name"] = service_name
            
        super().__init__(
            message=message,
            error_code="EXTERNAL_SERVICE_ERROR",
            details=error_details,
            status_code=status.HTTP_502_BAD_GATEWAY
        )


class RateLimitError(BaseATSException):
    """Exception for rate limit violations."""
    
    def __init__(
        self,
        message: str,
        limit: Optional[str] = None,
        reset_time: Optional[datetime] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """Initialize rate limit error.
        
        Args:
            message: Error message
            limit: Rate limit that was exceeded
            reset_time: When rate limit resets
            details: Additional error details
        """
        error_details = details or {}
        if limit:
            error_details["limit"] = limit
        if reset_time:
            error_details["reset_time"] = reset_time.isoformat()
            
        super().__init__(
            message=message,
            error_code="RATE_LIMIT_ERROR",
            details=error_details,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS
        )