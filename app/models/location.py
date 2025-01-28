"""Location-related data models."""
from typing import Dict, Optional
from pydantic import Field, EmailStr
from .base import BaseDBModel, PyObjectId

class LocationBase(BaseDBModel):
    """Base model for location data."""
    
    name: str = Field(..., min_length=2, max_length=100)
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    contact_name: str = Field(..., min_length=2, max_length=100)
    contact_phone: str = Field(..., pattern=r'^\+?[1-9]\d{1,14}$')
    contact_email: EmailStr

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "Visakhapatnam",
                "lat": 17.6868,
                "lng": 83.2185,
                "contact_name": "John Doe",
                "contact_phone": "+91-1234567890",
                "contact_email": "john@example.com"
            }
        }
    }

class LocationCreate(LocationBase):
    """Model for creating a new location."""
    pass

class Location(LocationBase):
    """Model for location with database fields."""
    
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    is_active: bool = True

    model_config = {
        "json_encoders": {
            PyObjectId: str
        }
    }

class LocationStats(BaseDBModel):
    """Model for location statistics."""
    
    total_vehicles: int = Field(default=0, ge=0)
    ats_centers: int = Field(default=0, ge=0)
    vehicles_under_8: int = Field(default=0, ge=0)
    vehicles_over_8: int = Field(default=0, ge=0)

class LocationResponse(BaseDBModel):
    """Model for location response with statistics."""
    
    name: str
    lat: float
    lng: float
    contact: Dict[str, str]
    stats: Dict[str, int]

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "Visakhapatnam",
                "lat": 17.6868,
                "lng": 83.2185,
                "contact": {
                    "name": "John Doe",
                    "phone": "+91-1234567890",
                    "email": "john@example.com"
                },
                "stats": {
                    "totalVehicles": 85,
                    "atsCenters": 5,
                    "vehiclesUnder8": 55,
                    "vehiclesOver8": 30
                }
            }
        }
    }