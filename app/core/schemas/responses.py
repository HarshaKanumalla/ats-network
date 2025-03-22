# backend/app/core/schemas/responses.py

from typing import Optional, Any, Generic, TypeVar
from pydantic import BaseModel
from datetime import datetime

T = TypeVar('T')

class BaseResponse(BaseModel, Generic[T]):
    status: str
    message: str
    timestamp: datetime = datetime.utcnow()
    data: Optional[T] = None
    
class ErrorResponse(BaseModel):
    status: str = "error"
    message: str
    error_code: str
    timestamp: datetime = datetime.utcnow()
    details: Optional[dict] = None
    path: Optional[str] = None