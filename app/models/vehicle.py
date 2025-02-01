#backend/app/models/vehicle.py

"""Vehicle-related data models."""
from typing import Optional, List, Dict, Any
from pydantic import Field, field_validator
from datetime import datetime, date
import re

from .common import AuditedModel, PyObjectId

class DocumentVerification(AuditedModel):
    """Document verification status tracking."""
    
    document_number: str = Field(..., min_length=5, max_length=50)
    document_type: str = Field(...)
    issue_date: Optional[date] = None
    expiry_date: Optional[date] = None
    issuing_authority: str = Field(...)
    
    verification_status: str = Field(default="pending")
    verified_by: Optional[PyObjectId] = None
    verified_at: Optional[datetime] = None
    verification_notes: Optional[str] = None
    document_url: Optional[str] = None

    class Config:
        json_encoders = {
            datetime: lambda dt: dt.isoformat() if dt else None,
            date: lambda d: d.isoformat() if d else None,
            PyObjectId: str
        }

class VehicleBase(AuditedModel):
    """Base vehicle model."""
    
    registration_number: str = Field(
        ...,
        description="Vehicle registration number",
        regex=r'^[A-Z]{2}[0-9]{2}[A-Z]{1,2}[0-9]{4}
    )
    vehicle_type: str = Field(..., description="Type of vehicle")
    manufacturing_year: int = Field(..., ge=1900, le=datetime.now().year)
    chassis_number: str = Field(..., min_length=17, max_length=17)
    engine_number: str = Field(..., min_length=6, max_length=20)
    
    # Owner information
    owner_info: Dict[str, str] = Field(
        ...,
        description="Vehicle owner information"
    )
    
    # Document verification
    rc_card: DocumentVerification
    fitness_certificate: Optional[DocumentVerification] = None
    insurance: DocumentVerification
    
    # Additional documents
    additional_documents: List[DocumentVerification] = Field(default_factory=list)
    
    # Test history
    last_test_date: Optional[datetime] = None
    next_test_due: Optional[datetime] = None
    test_history: List[PyObjectId] = Field(default_factory=list)

    @field_validator('registration_number')
    def validate_registration_number(cls, v: str) -> str:
        """Validate vehicle registration number format."""
        pattern = re.compile(r'^[A-Z]{2}[0-9]{2}[A-Z]{1,2}[0-9]{4})
        if not pattern.match(v):
            raise ValueError('Invalid registration number format')
        return v

    @field_validator('chassis_number')
    def validate_chassis_number(cls, v: str) -> str:
        """Validate chassis number format."""
        if not re.match(r'^[A-HJ-NPR-Z0-9]{17}, v):
            raise ValueError('Invalid chassis number format')
        return v

class VehicleCreate(VehicleBase):
    """Model for creating a new vehicle record."""
    
    # Document files will be handled separately through file upload
    rc_card_file: Optional[str] = None
    insurance_file: Optional[str] = None
    fitness_certificate_file: Optional[str] = None
    additional_files: List[str] = Field(default_factory=list)

class VehicleUpdate(VehicleBase):
    """Model for updating vehicle information."""
    
    registration_number: Optional[str] = None
    vehicle_type: Optional[str] = None
    manufacturing_year: Optional[int] = None
    chassis_number: Optional[str] = None
    engine_number: Optional[str] = None
    owner_info: Optional[Dict[str, str]] = None
    
    rc_card: Optional[DocumentVerification] = None
    fitness_certificate: Optional[DocumentVerification] = None
    insurance: Optional[DocumentVerification] = None

class VehicleInDB(VehicleBase):
    """Internal vehicle model with additional fields."""
    
    # Testing center references
    registered_center: PyObjectId = Field(
        ..., 
        description="Primary ATS center for the vehicle"
    )
    test_history_centers: List[PyObjectId] = Field(default_factory=list)
    
    # Document storage
    document_urls: Dict[str, str] = Field(default_factory=dict)
    
    # Status tracking
    verification_status: str = Field(default="pending")
    is_active: bool = Field(default=True)
    deactivation_reason: Optional[str] = None
    
    # Automated flags
    requires_testing: bool = Field(default=False)
    test_overdue: bool = Field(default=False)
    documents_expiring: bool = Field(default=False)
    
    class Config:
        json_encoders = {
            datetime: lambda dt: dt.isoformat() if dt else None,
            date: lambda d: d.isoformat() if d else None,
            PyObjectId: str
        }

class VehicleResponse(VehicleBase):
    """Vehicle information response model."""
    
    id: PyObjectId = Field(..., alias="_id")
    registered_center: Dict[str, Any] = Field(...)
    test_summary: Dict[str, Any] = Field(
        default_factory=lambda: {
            "total_tests": 0,
            "last_test_status": None,
            "next_due_date": None
        }
    )
    
    verification_status: str
    requires_testing: bool
    test_overdue: bool
    documents_expiring: bool
    
    class Config:
        json_encoders = {
            datetime: lambda dt: dt.isoformat() if dt else None,
            date: lambda d: d.isoformat() if d else None,
            PyObjectId: str
        }
        
    def dict(self, *args, **kwargs):
        """Customize dictionary representation."""
        d = super().dict(*args, **kwargs)
        # Remove sensitive or internal fields
        d.pop('document_urls', None)
        d.pop('deactivation_reason', None)
        return d
