# backend/app/core/middleware/error_handler.py

from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import HTTPException
from typing import Union, Dict, Any, Callable
import logging
from datetime import datetime
from uuid import uuid4

from ..exceptions import (
    ValidationError, 
    AuthenticationError,
    AuthorizationError,
    DatabaseError,
    TestError,
    CenterError,
    VehicleError,
    CustomException,
    FileOperationError,
    ConfigurationError
)

logger = logging.getLogger(__name__)

async def error_handler(
    request: Request,
    call_next: Callable
) -> Union[JSONResponse, Any]:
    try:
        response = await call_next(request)
        return response

    except HTTPException as e:
        return create_error_response(
            request=request,
            error=e.detail,
            status_code=e.status_code,
            error_code="HTTP_EXCEPTION"
        )

    except CustomException as e:
        return create_error_response(
            request=request,
            error=e,
            status_code=e.status_code,
            error_code=e.error_code
        )
        
    except ValidationError as e:
        return create_error_response(
            request=request,
            error=e,
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="VALIDATION_ERROR"
        )
        
    except AuthenticationError as e:
        return create_error_response(
            request=request,
            error=e,
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code="AUTHENTICATION_ERROR"
        )
        
    except AuthorizationError as e:
        return create_error_response(
            request=request,
            error=e,
            status_code=status.HTTP_403_FORBIDDEN,
            error_code="AUTHORIZATION_ERROR"
        )
        
    except DatabaseError as e:
        logger.error(f"Database error on {request.method} {request.url.path}: {str(e)}")
        return create_error_response(
            request=request,
            error=e,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_code="DATABASE_ERROR"
        )
        
    except (TestError, CenterError, VehicleError) as e:
        return create_error_response(
            request=request,
            error=e,
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="BUSINESS_LOGIC_ERROR"
        )
        
    except FileOperationError as e:
        logger.error(f"File operation error on {request.method} {request.url.path}: {str(e)}")
        return create_error_response(
            request=request,
            error=e,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_code="FILE_OPERATION_ERROR"
        )

    except ConfigurationError as e:
        logger.error(f"Configuration error on {request.method} {request.url.path}: {str(e)}")
        return create_error_response(
            request=request,
            error=e,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_code="CONFIGURATION_ERROR"
        )
        
    except Exception as e:
        logger.exception(f"Unhandled exception on {request.method} {request.url.path}")
        return create_error_response(
            request=request,
            error="Internal server error",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_code="INTERNAL_SERVER_ERROR"
        )

def create_error_response(
    request: Request,
    error: Union[Exception, str],
    status_code: int,
    error_code: str
) -> JSONResponse:
    message = str(error) if isinstance(error, Exception) else error
    
    content = {
        "status": "error",
        "message": message,
        "error_code": error_code,
        "timestamp": datetime.utcnow().isoformat(),
        "path": request.url.path,
        "method": request.method
    }

    if hasattr(error, 'details') and isinstance(error, Exception):
        content["details"] = error.details

    if status_code >= 500:
        content["request_id"] = get_request_id(request)

    return JSONResponse(
        status_code=status_code,
        content=content
    )

def get_request_id(request: Request) -> str:
    """Retrieve or generate a unique request ID for error tracking."""
    return request.headers.get("X-Request-ID", generate_request_id())

def generate_request_id() -> str:
    """Generate a unique request ID."""
    return str(uuid4())