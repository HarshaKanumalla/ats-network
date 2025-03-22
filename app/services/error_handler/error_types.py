# backend/app/services/error_handler/error_types.py

from typing import Dict, Any, Optional
from datetime import datetime

class WebSocketError(Exception):
    """Base exception for WebSocket errors."""
    def __init__(self, message: str, code: int = 4000, details: Optional[Dict[str, Any]] = None):
        self.message = message
        self.code = code
        self.details = details or {}
        self.timestamp = datetime.utcnow()
        super().__init__(self.message)

class ConnectionError(WebSocketError):
    """Error for connection-related issues."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code=4001, details=details)

class AuthenticationError(WebSocketError):
    """Error for WebSocket authentication failures."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code=4002, details=details)

class SessionError(WebSocketError):
    """Error for session-related issues."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code=4003, details=details)

class TestMonitoringError(Exception):
    """Base exception for test monitoring errors."""
    def __init__(self, message: str, code: str = "TEST_ERROR", details: Optional[Dict[str, Any]] = None):
        self.message = message
        self.code = code 
        self.details = details or {}
        self.timestamp = datetime.utcnow()
        super().__init__(self.message)

class ValidationError(TestMonitoringError):
    """Error for test data validation failures."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="VALIDATION_ERROR", details=details)

class ThresholdError(TestMonitoringError):
    """Error for test threshold violations."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="THRESHOLD_ERROR", details=details)