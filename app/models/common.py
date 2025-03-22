#backend/app/models/common.py

"""Common base models and utilities for data handling."""
from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel as PydanticBaseModel, ConfigDict, Field, validator
from bson import ObjectId

class PyObjectId(str):
    """Custom type for handling MongoDB ObjectIds."""
    
    @classmethod
    def __get_validators__(cls):
        yield cls.validate
        
    @classmethod
    def validate(cls, value: Any) -> str:
        try:
            if isinstance(value, ObjectId):
                return str(value)
            if ObjectId.is_valid(value):
                return str(ObjectId(value))
            raise ValueError("Invalid ObjectId")
        except Exception as e:
            raise ValueError(f"ObjectId validation error: {str(e)}")

class BaseModel(PydanticBaseModel):
    """Base model with enhanced configuration."""
    
    model_config = ConfigDict(
        populate_by_name=True,
        validate_assignment=True,
        arbitrary_types_allowed=True,
        json_encoders={
            ObjectId: str,
            datetime: lambda dt: dt.isoformat()
        }
    )

class TimestampedModel(BaseModel):
    """Base model with timestamp fields and monitoring."""
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_modified_by: Optional[PyObjectId] = None
    
    def update_timestamp(self, modified_by: Optional[str] = None) -> None:
        """Update the updated_at timestamp and modifier."""
        self.updated_at = datetime.utcnow()
        if modified_by:
            self.last_modified_by = PyObjectId(modified_by)

class DocumentModel(TimestampedModel):
    """Base model for document-based models with enhanced tracking."""
    
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    is_active: bool = Field(default=True)
    version: int = Field(default=1)
    
    def dict(self, *args, **kwargs):
        """Override dict method to handle ID field."""
        doc = super().dict(*args, **kwargs)
        if '_id' in doc and doc['_id']:
            doc['_id'] = str(doc['_id'])
        return doc

    @property
    def object_id(self) -> ObjectId:
        """Get the BSON ObjectId."""
        return ObjectId(self.id) if self.id else None

class StatusModel(DocumentModel):
    """Base model for status-tracked models with history."""
    
    status: str = Field(..., description="Current status of the record")
    status_history: list[dict] = Field(default_factory=list)
    
    def update_status(self, new_status: str, updated_by: str, reason: Optional[str] = None) -> None:
        """Update status with history tracking."""
        if new_status != self.status:
            self.status_history.append({
                "previous_status": self.status,
                "new_status": new_status,
                "updated_by": updated_by,
                "reason": reason,
                "updated_at": datetime.utcnow()
            })
            self.status = new_status
            self.update_timestamp(updated_by)

class MetadataModel(DocumentModel):
    """Base model for metadata-tracked models with versioning."""
    
    metadata: dict = Field(default_factory=dict)
    
    def update_metadata(self, updates: dict, updated_by: str) -> None:
        """Update metadata fields with tracking."""
        self.metadata.update(updates)
        self.metadata["last_updated"] = datetime.utcnow()
        self.metadata["updated_by"] = updated_by
        self.version += 1
        self.update_timestamp(updated_by)

class AuditedModel(StatusModel, MetadataModel):
    """Base model with comprehensive auditing support."""
    
    created_by: Optional[PyObjectId] = None
    updated_by: Optional[PyObjectId] = None
    
    def update_audit_trail(self, updated_by: str, action: str, details: Optional[dict] = None) -> None:
        """Update audit trail information."""
        self.updated_by = PyObjectId(updated_by)
        self.version += 1
        self.metadata.setdefault("audit_trail", []).append({
            "action": action,
            "details": details or {},
            "performed_by": updated_by,
            "timestamp": datetime.utcnow()
        })
        self.update_timestamp(updated_by)