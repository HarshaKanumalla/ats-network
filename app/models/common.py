#backend/app/models/common.py

"""Common base models and utilities for data handling."""
from datetime import datetime
from typing import Optional, Any, List, Dict
from pydantic import BaseModel as PydanticBaseModel, ConfigDict, Field, validator
from bson import ObjectId
import logging

logger = logging.getLogger(__name__)

class ValidationError(Exception):
    """Custom validation error."""
    pass

class StateError(Exception):
    """Invalid state transition error."""
    pass

class AuditError(Exception):
    """Audit trail error."""
    pass

class PyObjectId(str):
    """Custom type for handling MongoDB ObjectIds."""
    
    @classmethod
    def __get_validators__(cls):
        yield cls.validate
        
    @classmethod
    def validate(cls, value: Any) -> str:
        try:
            if value is None:
                raise ValueError("ObjectId cannot be None")
            if isinstance(value, str) and not value.strip():
                raise ValueError("ObjectId cannot be empty")
            if isinstance(value, ObjectId):
                return str(value)
            if ObjectId.is_valid(value):
                return str(ObjectId(value))
            raise ValueError("Invalid ObjectId")
        except Exception as e:
            logger.error(f"ObjectId validation error: {str(e)}")
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
    
    @validator('updated_at')
    def validate_timestamps(cls, v, values):
        if 'created_at' in values and v < values['created_at']:
            raise ValueError("updated_at cannot be before created_at")
        return v

    @validator('last_modified_by')
    def validate_modifier(cls, v):
        if v and not ObjectId.is_valid(str(v)):
            raise ValueError("Invalid last_modified_by ID")
        return v
    
    def update_timestamp(self, modified_by: Optional[str] = None) -> None:
        """Update the updated_at timestamp and modifier."""
        try:
            self.updated_at = datetime.utcnow()
            if modified_by:
                self.last_modified_by = PyObjectId(modified_by)
            logger.debug(f"Updated timestamp for {self.__class__.__name__}")
        except Exception as e:
            logger.error(f"Failed to update timestamp: {str(e)}")
            raise ValidationError(f"Failed to update timestamp: {str(e)}")

class DocumentModel(TimestampedModel):
    """Base model for document-based models with enhanced tracking."""
    
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    is_active: bool = Field(default=True)
    version: int = Field(default=1, ge=1)
    
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

    def increment_version(self) -> None:
        """Increment document version."""
        self.version += 1
        logger.debug(f"Incremented version to {self.version} for {self.__class__.__name__}")

class StatusModel(DocumentModel):
    """Base model for status-tracked models with history."""
    
    VALID_STATUSES = ['draft', 'active', 'inactive', 'archived']
    status: str = Field(..., description="Current status of the record")
    status_history: List[Dict] = Field(default_factory=list)
    
    @validator('status')
    def validate_status(cls, v):
        if v not in cls.VALID_STATUSES:
            raise ValueError(f"Invalid status. Must be one of: {cls.VALID_STATUSES}")
        return v

    def can_transition_to(self, new_status: str) -> bool:
        """Check if status transition is allowed."""
        transitions = {
            'draft': ['active'],
            'active': ['inactive', 'archived'],
            'inactive': ['active', 'archived'],
            'archived': []
        }
        return new_status in transitions.get(self.status, [])
    
    def update_status(self, new_status: str, updated_by: str, reason: Optional[str] = None) -> None:
        """Update status with history tracking."""
        try:
            if not self.can_transition_to(new_status):
                raise StateError(f"Invalid status transition from {self.status} to {new_status}")
            
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
                logger.info(f"Status updated to {new_status} for {self.__class__.__name__}")
        except Exception as e:
            logger.error(f"Status update failed: {str(e)}")
            raise StateError(f"Failed to update status: {str(e)}")

class MetadataModel(DocumentModel):
    """Base model for metadata-tracked models with versioning."""
    
    metadata: Dict = Field(default_factory=dict)
    
    @validator('metadata')
    def validate_metadata(cls, v):
        if not isinstance(v, dict):
            raise ValueError("Metadata must be a dictionary")
        if len(v) > 100:  # Reasonable limit
            raise ValueError("Metadata too large")
        return v

    def validate_metadata_update(self, updates: Dict) -> None:
        """Validate metadata updates."""
        if not updates:
            raise ValueError("Updates cannot be empty")
        if not isinstance(updates, dict):
            raise ValueError("Updates must be a dictionary")
        if len(self.metadata) + len(updates) > 100:
            raise ValueError("Metadata would exceed size limit")
    
    def update_metadata(self, updates: Dict, updated_by: str) -> None:
        """Update metadata fields with tracking."""
        try:
            self.validate_metadata_update(updates)
            self.metadata.update(updates)
            self.metadata["last_updated"] = datetime.utcnow()
            self.metadata["updated_by"] = updated_by
            self.increment_version()
            self.update_timestamp(updated_by)
            logger.info(f"Metadata updated for {self.__class__.__name__}")
        except Exception as e:
            logger.error(f"Metadata update failed: {str(e)}")
            raise ValidationError(f"Failed to update metadata: {str(e)}")

class AuditedModel(StatusModel, MetadataModel):
    """Base model with comprehensive auditing support."""
    
    VALID_ACTIONS = ['create', 'update', 'delete', 'archive']
    created_by: Optional[PyObjectId] = None
    updated_by: Optional[PyObjectId] = None
    
    @validator('created_by', 'updated_by')
    def validate_user_ids(cls, v):
        if v and not ObjectId.is_valid(str(v)):
            raise ValueError("Invalid user ID")
        return v

    def validate_audit_action(self, action: str) -> None:
        """Validate audit action."""
        if action not in self.VALID_ACTIONS:
            raise ValueError(f"Invalid action. Must be one of: {self.VALID_ACTIONS}")

    def get_audit_trail(self) -> List[Dict]:
        """Get formatted audit trail."""
        return self.metadata.get("audit_trail", [])
    
    def update_audit_trail(self, updated_by: str, action: str, details: Optional[Dict] = None) -> None:
        """Update audit trail information."""
        try:
            self.validate_audit_action(action)
            self.updated_by = PyObjectId(updated_by)
            self.increment_version()
            
            audit_entry = {
                "action": action,
                "details": details or {},
                "performed_by": updated_by,
                "timestamp": datetime.utcnow()
            }
            
            self.metadata.setdefault("audit_trail", []).append(audit_entry)
            self.update_timestamp(updated_by)
            logger.info(f"Audit trail updated: {action} by {updated_by}")
        except Exception as e:
            logger.error(f"Failed to update audit trail: {str(e)}")
            raise AuditError(f"Failed to update audit trail: {str(e)}")