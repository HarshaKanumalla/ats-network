"""Base models and shared functionality."""
from typing import Any
from pydantic import BaseModel, ConfigDict
from datetime import datetime
from bson import ObjectId
from pydantic_core import core_schema

class PyObjectId(str):
    """Custom type for handling MongoDB ObjectId."""

    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, value: Any) -> str:
        if isinstance(value, ObjectId):
            return str(value)
        if ObjectId.is_valid(value):
            return str(ObjectId(value))
        raise ValueError("Invalid ObjectId")

    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        _source_type: Any,
        _handler: Any
    ) -> core_schema.CoreSchema:
        return core_schema.json_or_python_schema(
            json_schema=core_schema.str_schema(),
            python_schema=core_schema.union_schema([
                core_schema.str_schema(),
                core_schema.is_instance_schema(ObjectId),
            ]),
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda x: str(x) if isinstance(x, ObjectId) else x,
                return_schema=core_schema.str_schema(),
            ),
        )

class BaseDBModel(BaseModel):
    """Base model for all database models."""
    
    created_at: datetime = None
    updated_at: datetime = None

    model_config = ConfigDict(
        populate_by_name=True,
        validate_assignment=True,
        arbitrary_types_allowed=True,
        json_schema_extra={
            "example": {
                "created_at": "2024-01-23T00:00:00Z",
                "updated_at": "2024-01-23T00:00:00Z"
            }
        }
    )

    def pre_save(self) -> None:
        """Prepare model for saving to database."""
        current_time = datetime.utcnow()
        if not self.created_at:
            self.created_at = current_time
        self.updated_at = current_time