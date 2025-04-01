from typing import Dict, Any, Optional, Callable
import logging
from datetime import datetime
from fastapi import WebSocket
import traceback
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
        """
        Handle WebSocket errors with appropriate responses.

        Args:
            websocket (WebSocket): The WebSocket connection.
            error (WebSocketError): The WebSocket error to handle.
            session_id (Optional[str]): The session ID associated with the error.

        Returns:
            None
        """
        try:
            if not isinstance(error, WebSocketError):
                logger.error(f"Invalid error type: {type(error).__name__}")
                raise ValueError("Invalid error type provided")

            if not isinstance(error.code, int) or not (1000 <= error.code <= 4999):
                logger.error(f"Invalid WebSocket error code: {error.code}")
                error.code = 1000  # Default to normal closure

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
            else:
                logger.warning("Attempted to close an already closed WebSocket connection.")

            logger.error(f"WebSocket error: {error.message}", 
                         extra={"error_details": error.details})

        except Exception as e:
            logger.critical(f"Error handler failure: {str(e)}")

    @staticmethod
    async def handle_test_error(
        error: TestMonitoringError,
        notify_callback: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """
        Handle test monitoring errors with notifications.

        Args:
            error (TestMonitoringError): The test monitoring error to handle.
            notify_callback (Optional[Callable]): Callback for sending notifications.

        Returns:
            Dict[str, Any]: Error data.
        """
        try:
            if not isinstance(error, TestMonitoringError):
                logger.error(f"Invalid error type: {type(error).__name__}")
                raise ValueError("Invalid error type provided")

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
                try:
                    await notify_callback(error_data)
                except Exception as notify_error:
                    logger.error(f"Notification callback failed: {str(notify_error)}")

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
        """
        Log error with enhanced context.

        Args:
            error (Exception): The error to log.
            context (Dict[str, Any]): Additional context for the error.

        Returns:
            None
        """
        try:
            error_data = {
                "error_type": error.__class__.__name__,
                "message": str(error),
                "timestamp": datetime.utcnow().isoformat(),
                "context": context,
                "traceback": traceback.format_exc()
            }

            if hasattr(error, 'details') and isinstance(error.details, dict):
                error_data["details"] = error.details
            else:
                error_data["details"] = "No additional details provided"

            logger.error("Error occurred", extra=error_data)

        except Exception as e:
            logger.critical(f"Logging failure: {str(e)}")

    @staticmethod
    async def handle_system_error(
        error: Exception,
        notify_callback: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """
        Handle generic system-wide errors.

        Args:
            error (Exception): The system-wide error to handle.
            notify_callback (Optional[Callable]): Callback for sending notifications.

        Returns:
            Dict[str, Any]: Error data.
        """
        try:
            error_data = {
                "type": "system_error",
                "error_type": error.__class__.__name__,
                "message": str(error),
                "timestamp": datetime.utcnow().isoformat(),
                "traceback": traceback.format_exc()
            }

            # Log error
            logger.critical("System-wide error occurred", extra=error_data)

            # Send notification if callback provided
            if notify_callback:
                try:
                    await notify_callback(error_data)
                except Exception as notify_error:
                    logger.error(f"Notification callback failed: {str(notify_error)}")

            return error_data

        except Exception as e:
            logger.critical(f"System error handler failure: {str(e)}")
            return {
                "type": "system_error",
                "message": "Internal error handling failure",
                "timestamp": datetime.utcnow().isoformat()
            }