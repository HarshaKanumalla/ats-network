"""Request logging middleware."""
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
import logging
import time
import json
from typing import Any, Dict

logger = logging.getLogger(__name__)

class RequestLogger(BaseHTTPMiddleware):
    """Handles request logging and performance monitoring."""

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        """Log request details and timing."""
        start_time = time.time()
        
        try:
            await self._log_request_details(request)
            response = await call_next(request)
            await self._log_response_details(response, start_time)
            return response
            
        except Exception as e:
            logger.error("Request processing error:", exc_info=True)
            raise

    async def _log_request_details(self, request: Request) -> None:
        """Log incoming request details."""
        log_data = {
            "method": request.method,
            "path": request.url.path,
            "headers": dict(request.headers),
            "client": request.client.host if request.client else None
        }

        if request.url.path == "/auth/login":
            try:
                body = await request.body()
                log_data["body"] = body.decode()
            except Exception as e:
                logger.error(f"Error reading request body: {str(e)}")

        logger.info("Incoming request: %s", json.dumps(log_data))

    async def _log_response_details(self, response: Any, start_time: float) -> None:
        """Log response details and timing."""
        process_time = time.time() - start_time
        log_data = {
            "status_code": response.status_code,
            "process_time": f"{process_time:.2f}s",
            "headers": dict(response.headers)
        }
        
        logger.info("Response details: %s", json.dumps(log_data))