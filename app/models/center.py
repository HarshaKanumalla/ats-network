#backend/app/models/center.py

"""ATS center-related data models and validation schemas."""
from typing import Optional, List, Dict, Any
from pydantic import EmailStr, Field, field_validator
from datetime import datetime

from .common import AuditedModel, PyObjectId
from .location import Location

class CenterBase(AuditedModel):
    """Base model for ATS center data."""
    
    name: str = Field(..., min_length=3, max_length=100)
    center_code: str = Field(..., pattern=r'^ATS\d{6}$')
    
    # Address details
    address: str = Field(..., min_length=5, max_length=200)
    city: str = Field(..., min_length=2, max_length=100)
    district: str = Field(..., min_length=2, max_length=100)
    state: str = Field(..., min_length=2, max_length=100)
    pin_code: str = Field(..., pattern=r'^\d{6}$')
    
    # Location coordinates
    location: Location
    
    # Contact information
    contact_person: str = Field(..., min_length=2, max_length=100)
    contact_email: EmailStr
    contact_phone: str = Field(..., pattern=r'^\+?[1-9]\d{9,14}$')
    
    # Operating details
    working_hours: Dict[str, str] = Field(
        default_factory=lambda: {
            "monday": "09:00-17:00",
            "tuesday": "09:00-17:00",
            "wednesday": "09:00-17:00",
            "thursday": "09:00-17:00",
            "friday": "09:00-17:00",
            "saturday": "09:00-13:00",
            "sunday": "closed"
        }
    )
    
    capacity_per_day: int = Field(default=50, ge=1, le=200)
    is_active: bool = Field(default=True)

class CenterCreate(CenterBase):
    """Model for creating a new ATS center."""
    
    owner_id: PyObjectId = Field(...)
    business_license: str = Field(..., min_length=5, max_length=50)
    
    @field_validator('center_code')
    def validate_center_code(cls, v):
        """Validate center code format."""
        if not v.startswith('ATS'):
            raise ValueError('Center code must start with ATS')
        if not v[3:].isdigit():
            raise ValueError('Center code must end with 6 digits')
        return v

class CenterUpdate(CenterBase):
    """Model for updating center information."""
    
    name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    state: Optional[str] = None
    pin_code: Optional[str] = None
    location: Optional[Location] = None
    contact_person: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    contact_phone: Optional[str] = None
    working_hours: Optional[Dict[str, str]] = None
    capacity_per_day: Optional[int] = None
    is_active: Optional[bool] = None

class CenterInDB(CenterBase):
    """Internal center model with additional fields."""
    
    owner_id: PyObjectId
    business_license: str
    approval_status: str = Field(default="pending")
    approved_by: Optional[PyObjectId] = None
    approved_at: Optional[datetime] = None
    
    # Equipment details
    testing_equipment: List[Dict[str, Any]] = Field(default_factory=list)
    equipment_details: Dict[str, Any] = Field(
        default_factory=lambda: {
            "speed": {
                "serial_number": None,
                "last_calibration": None,
                "next_calibration": None,
                "status": "pending"
            },
            "brake": {
                "serial_number": None,
                "last_calibration": None,
                "next_calibration": None,
                "status": "pending"
            },
            "noise": {
                "serial_number": None,
                "last_calibration": None,
                "next_calibration": None,
                "status": "pending"
            },
            "headlight": {
                "serial_number": None,
                "last_calibration": None,
                "next_calibration": None,
                "status": "pending"
            },
            "axle": {
                "serial_number": None,
                "last_calibration": None,
                "next_calibration": None,
                "status": "pending"
            }
        }
    )

    # Document references
    documents: List[Dict[str, str]] = Field(default_factory=list)
    
    # Testing statistics
    test_statistics: Dict[str, Any] = Field(
        default_factory=lambda: {
            "total_tests": 0,
            "tests_today": 0,
            "tests_this_month": 0,
            "vehicles_under_8": 0,
            "vehicles_over_8": 0,
            "last_updated": datetime.utcnow()
        }
    )

    # Staff members
    staff_members: List[PyObjectId] = Field(default_factory=list)
    
    class Config:
        json_encoders = {
            datetime: lambda dt: dt.isoformat() if dt else None,
            PyObjectId: str
        }

class CenterResponse(CenterBase):
    """Center information response model."""
    
    id: PyObjectId = Field(..., alias="_id")
    owner_id: PyObjectId
    approval_status: str
    test_statistics: Dict[str, Any]
    
    # Include only necessary equipment status
    equipment_status: Dict[str, str] = Field(default_factory=dict)
    
    class Config:
        json_encoders = {
            PyObjectId: str,
            datetime: lambda dt: dt.isoformat() if dt else None
        }
        
    def dict(self, *args, **kwargs):
        """Customize dictionary representation."""
        d = super().dict(*args, **kwargs)
        # Transform equipment details into simple status
        if 'equipment_details' in d:
            d['equipment_status'] = {
                key: details['status']
                for key, details in d['equipment_details'].items()
            }
            d.pop('equipment_details')
        return d

class CenterStatistics(AuditedModel):
    """Detailed center statistics model."""
    
    center_id: PyObjectId
    total_vehicles: int = 0
    vehicles_under_8: int = 0
    vehicles_over_8: int = 0
    
    # Test statistics
    test_counts: Dict[str, int] = Field(default_factory=dict)
    monthly_stats: Dict[str, Dict[str, int]] = Field(default_factory=dict)
    daily_stats: Dict[str, Dict[str, int]] = Field(default_factory=dict)
    
    # Performance metrics
    average_test_duration: float = 0.0
    success_rate: float = 0.0
    utilization_rate: float = 0.0
    
    # Time period
    start_date: datetime
    end_date: datetime
    
    class Config:
        json_encoders = {
            datetime: lambda dt: dt.isoformat() if dt else None,
            PyObjectId: str
        }

class CenterEquipment(AuditedModel):
    """Equipment management model."""
    
    center_id: PyObjectId
    equipment_type: str = Field(..., description="Type of testing equipment")
    serial_number: str = Field(..., min_length=5, max_length=50)
    manufacturer: str = Field(..., min_length=2, max_length=100)
    model_number: str = Field(..., min_length=2, max_length=50)
    
    # Calibration details
    last_calibration: datetime
    next_calibration: datetime
    calibration_agency: str = Field(..., min_length=2, max_length=100)
    calibration_certificate: str = Field(...)
    
    # Status tracking
    status: str = Field(default="active")
    maintenance_history: List[Dict[str, Any]] = Field(default_factory=list)
    
    # Document references
    documents: List[str] = Field(default_factory=list)
    
    class Config:
        json_encoders = {
            datetime: lambda dt: dt.isoformat() if dt else None,
            PyObjectId: str
        }

class CenterDocument(AuditedModel):
    """Center document management model."""
    
    center_id: PyObjectId
    document_type: str = Field(..., description="Type of document")
    file_name: str = Field(..., min_length=1, max_length=255)
    file_url: str = Field(..., min_length=1)
    mime_type: str = Field(..., min_length=1)
    file_size: int = Field(..., gt=0)
    
    # Verification details
    verification_status: str = Field(default="pending")
    verified_by: Optional[PyObjectId] = None
    verified_at: Optional[datetime] = None
    verification_notes: Optional[str] = None
    
    class Config:
        json_encoders = {
            datetime: lambda dt: dt.isoformat() if dt else None,
            PyObjectId: str
        }
