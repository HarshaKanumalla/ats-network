# backend/app/middleware/logging.py

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
import logging
import time
import traceback
import json

logger = logging.getLogger(__name__)

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        
        try:
            # Log request details
            logger.info(f"Incoming request: {request.method} {request.url.path}")
            logger.info(f"Request headers: {dict(request.headers)}")
            
            # For specific endpoints, log request body
            if request.url.path == "/auth/login":
                try:
                    body = await request.body()
                    logger.info(f"Request body for {request.url.path}: {body.decode()}")
                except Exception as e:
                    logger.error(f"Error reading request body: {str(e)}")

            # Process the request
            response = await call_next(request)
            
            # Log response details
            process_time = time.time() - start_time
            status_code = response.status_code
            logger.info(f"Response status: {status_code}")
            logger.info(f"Request completed in {process_time:.2f}s")
            
            return response
            
        except Exception as e:
            logger.error("Exception in request processing:")
            logger.error(f"Error details: {str(e)}")
            logger.error(f"Stack trace: {traceback.format_exc()}")
            raise