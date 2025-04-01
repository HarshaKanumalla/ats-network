from typing import Dict, Any, Optional
from datetime import datetime
import logging

class BaseError(Exception):
    """Base exception for all custom errors."""
    def __init__(self, message: str, code: int, details: Optional[Dict[str, Any]] = None):
        self.message = message
        self.code = code
        self.details = details or {}
        self.timestamp = datetime.utcnow()
        super().__init__(self.message)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize error details to a dictionary."""
        return {
            "message": self.message,
            "code": self.code,
            "details": self.details,
            "timestamp": self.timestamp.isoformat()
        }

    def log(self, logger: logging.Logger) -> None:
        """Log the error details."""
        logger.error(f"Error occurred: {self.message}", extra=self.to_dict())

class WebSocketError(BaseError):
    """Base exception for WebSocket errors."""
    def __init__(self, message: str, code: int = 4000, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code, details)

class ConnectionError(WebSocketError):
    """Error for connection-related issues."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        default_details = {"reason": "Connection lost"}
        if details:
            default_details.update(details)
        super().__init__(message, code=4001, details=default_details)

class AuthenticationError(WebSocketError):
    """Error for WebSocket authentication failures."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code=4002, details=details)

class SessionError(WebSocketError):
    """Error for session-related issues."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code=4003, details=details)

class TestMonitoringError(BaseError):
    """Base exception for test monitoring errors."""
    def __init__(self, message: str, code: int = 5000, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code, details)

class ValidationError(TestMonitoringError):
    """Error for test data validation failures."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code=5001, details=details)

class ThresholdError(TestMonitoringError):
    """Error for test threshold violations."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code=5002, details=details)