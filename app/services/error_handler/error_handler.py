# backend/app/services/error_handler/error_handler.py

from typing import Dict, Any, Optional, Callable
import logging
from datetime import datetime
from fastapi import WebSocket
from .error_types import *

logger = logging.getLogger(__name__)

class ErrorHandler:
    """Centralized error handling for WebSocket and test monitoring."""

    @staticmethod
    async def handle_websocket_error(
        websocket: WebSocket,
        error: WebSocketError,
        session_id: Optional[str] = None
    ) -> None:
        """Handle WebSocket errors with appropriate responses."""
        try:
            error_response = {
                "type": "error",
                "code": error.code,
                "message": error.message,
                "timestamp": datetime.utcnow().isoformat(),
                "details": error.details
            }

            if session_id:
                error_response["session_id"] = session_id

            if not websocket.closed:
                await websocket.send_json(error_response)
                await websocket.close(code=error.code)

            logger.error(f"WebSocket error: {error.message}", 
                        extra={"error_details": error.details})

        except Exception as e:
            logger.critical(f"Error handler failure: {str(e)}")

    @staticmethod
    async def handle_test_error(
        error: TestMonitoringError,
        notify_callback: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """Handle test monitoring errors with notifications."""
        try:
            error_data = {
                "type": "test_error",
                "code": error.code,
                "message": error.message,
                "timestamp": datetime.utcnow().isoformat(),
                "details": error.details
            }

            # Log error
            logger.error(f"Test monitoring error: {error.message}", 
                        extra={"error_details": error.details})

            # Send notification if callback provided
            if notify_callback:
                await notify_callback(error_data)

            return error_data

        except Exception as e:
            logger.critical(f"Error handler failure: {str(e)}")
            return {
                "type": "system_error",
                "message": "Internal error handling failure",
                "timestamp": datetime.utcnow().isoformat()
            }

    @staticmethod
    def log_error(
        error: Exception,
        context: Dict[str, Any]
    ) -> None:
        """Log error with enhanced context."""
        try:
            error_data = {
                "error_type": error.__class__.__name__,
                "message": str(error),
                "timestamp": datetime.utcnow().isoformat(),
                "context": context
            }

            if hasattr(error, 'details'):
                error_data["details"] = error.details

            logger.error("Error occurred", extra=error_data)

        except Exception as e:
            logger.critical(f"Logging failure: {str(e)}")