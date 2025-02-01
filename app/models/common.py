#backend/app/models/common.py

"""Common base models and utilities."""
from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel as PydanticBaseModel, ConfigDict, Field
from bson import ObjectId

class PyObjectId(str):
    """Custom type for handling MongoDB ObjectIds."""
    
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

class BaseModel(PydanticBaseModel):
    """Base model with common configuration and methods."""
    
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
    """Base model with timestamp fields."""
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    def update_timestamp(self) -> None:
        """Update the updated_at timestamp."""
        self.updated_at = datetime.utcnow()

class DocumentModel(TimestampedModel):
    """Base model for document-based models."""
    
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    
    def dict(self, *args, **kwargs):
        """Override dict method to handle ID field."""
        doc = super().dict(*args, **kwargs)
        # Convert _id to string format if present
        if '_id' in doc and doc['_id']:
            doc['_id'] = str(doc['_id'])
        return doc

    @property
    def object_id(self) -> ObjectId:
        """Get the BSON ObjectId."""
        return ObjectId(self.id) if self.id else None

class StatusModel(DocumentModel):
    """Base model for status-tracked models."""
    
    status: str = Field(..., description="Current status of the record")
    status_history: list[dict] = Field(default_factory=list)
    
    def update_status(self, new_status: str, updated_by: str) -> None:
        """Update status with history tracking.
        
        Args:
            new_status: New status to set
            updated_by: ID of user making the change
        """
        if new_status != self.status:
            self.status_history.append({
                "status": self.status,
                "updated_at": self.updated_at,
                "updated_by": updated_by
            })
            self.status = new_status
            self.update_timestamp()

class MetadataModel(DocumentModel):
    """Base model for metadata-tracked models."""
    
    metadata: dict = Field(default_factory=dict)
    
    def update_metadata(self, updates: dict) -> None:
        """Update metadata fields.
        
        Args:
            updates: Dictionary of metadata updates
        """
        self.metadata.update(updates)
        self.update_timestamp()

class AuditedModel(StatusModel):
    """Base model with full auditing support."""
    
    created_by: Optional[PyObjectId] = None
    updated_by: Optional[PyObjectId] = None
    version: int = 1
    
    def update_audit_trail(self, updated_by: str) -> None:
        """Update audit trail information.
        
        Args:
            updated_by: ID of user making the change
        """
        self.updated_by = PyObjectId(updated_by)
        self.version += 1
        self.update_timestamp()