"""Error handling middleware."""
from fastapi import Request, status
from fastapi.responses import JSONResponse
import logging
from typing import Callable, Dict, Any
import traceback

logger = logging.getLogger(__name__)

class ErrorHandler:
    """Handles application-wide error processing."""

    @staticmethod
    async def handle_error(request: Request, call_next: Callable) -> JSONResponse:
        """Process requests and handle any errors that occur."""
        try:
            return await call_next(request)
        except Exception as e:
            return await ErrorHandler._process_error(e, request)

    @staticmethod
    async def _process_error(error: Exception, request: Request) -> JSONResponse:
        """Process and format error responses."""
        error_details = {
            "path": request.url.path,
            "method": request.method,
            "error_type": error.__class__.__name__,
            "error_message": str(error)
        }
        
        logger.error(
            "Request processing error: %s",
            error_details,
            extra={"error_traceback": traceback.format_exc()}
        )

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "An internal server error occurred"}
        )

    @staticmethod
    def format_error_response(
        status_code: int,
        message: str,
        details: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Format error response consistently."""
        response = {
            "status": "error",
            "message": message,
            "code": status_code
        }
        
        if details:
            response["details"] = details
            
        return response