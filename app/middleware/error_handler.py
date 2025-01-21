# backend/app/middleware/error_handler.py

from fastapi import Request
from fastapi.responses import JSONResponse
import logging
from typing import Callable

logger = logging.getLogger(__name__)

async def error_handling_middleware(request: Request, call_next: Callable):
    try:
        response = await call_next(request)
        return response
    except Exception as e:
        logger.error(f"Unhandled error: {str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"detail": str(e)}
        )