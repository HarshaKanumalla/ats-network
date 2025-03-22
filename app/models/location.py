#backend/app/models/location.py

"""Location and geographical data models with enhanced validation."""
from typing import Optional, List, Dict, Any
from pydantic import Field, validator, field_validator
from datetime import datetime

from .common import AuditedModel, PyObjectId
from ..config import get_settings

settings = get_settings()

class Coordinates(AuditedModel):
    """Geographic coordinates model with validation."""
    
    latitude: float = Field(
        ...,
        ge=settings.MAP_BOUNDS["south"],
        le=settings.MAP_BOUNDS["north"],
        description="Latitude in decimal degrees"
    )
    longitude: float = Field(
        ...,
        ge=settings.MAP_BOUNDS["west"],
        le=settings.MAP_BOUNDS["east"],
        description="Longitude in decimal degrees"
    )
    accuracy: Optional[float] = Field(
        default=None,
        description="Accuracy of coordinates in meters"
    )
    
    @field_validator('latitude')
    def validate_latitude(cls, v: float) -> float:
        """Validate latitude is within India's bounds."""
        if not (settings.MAP_BOUNDS['south'] <= v <= settings.MAP_BOUNDS['north']):
            raise ValueError('Latitude outside India\'s geographical bounds')
        return round(v, 6)  # 6 decimal places for ~10cm precision

    @field_validator('longitude')
    def validate_longitude(cls, v: float) -> float:
        """Validate longitude is within India's bounds."""
        if not (settings.MAP_BOUNDS['west'] <= v <= settings.MAP_BOUNDS['east']):
            raise ValueError('Longitude outside India\'s geographical bounds')
        return round(v, 6)

class Address(AuditedModel):
    """Enhanced address model with validation."""
    
    street: str = Field(..., min_length=5, max_length=200)
    area: Optional[str] = Field(default=None, max_length=100)
    landmark: Optional[str] = Field(default=None, max_length=100)
    city: str = Field(..., min_length=2, max_length=100)
    district: str = Field(..., min_length=2, max_length=100)
    state: str = Field(..., min_length=2, max_length=100)
    pin_code: str = Field(..., pattern=r'^\d{6}$')
    
    @field_validator('pin_code')
    def validate_pin_code(cls, v: str) -> str:
        """Validate PIN code format and existence."""
        if not v.isdigit() or len(v) != 6:
            raise ValueError("Invalid PIN code format")
        # Additional PIN code validation could be added here
        return v

class Location(AuditedModel):
    """Comprehensive location model with address and coordinates."""
    
    coordinates: Coordinates
    address: Address
    
    # Additional location metadata
    place_id: Optional[str] = None
    formatted_address: Optional[str] = None
    location_type: Optional[str] = Field(
        default="business",
        description="Type of location (business, residential, etc.)"
    )
    
    # Verification status
    verification_status: str = Field(
        default="pending",
        description="Location verification status"
    )
    verified_by: Optional[PyObjectId] = None
    verified_at: Optional[datetime] = None
    
    # Additional metadata
    timezone: Optional[str] = None
    administrative_area: Optional[Dict[str, str]] = None
    
    class Config:
        json_encoders = {
            datetime: lambda dt: dt.isoformat() if dt else None,
            PyObjectId: str
        }

class LocationCreate(AuditedModel):
    """Model for creating a new location record."""
    
    address: Address
    coordinates: Optional[Coordinates] = None  # Optional as it might be geocoded later
    center_id: Optional[PyObjectId] = None
    metadata: Optional[Dict[str, Any]] = None

class LocationUpdate(AuditedModel):
    """Model for updating location information."""
    
    address: Optional[Address] = None
    coordinates: Optional[Coordinates] = None
    verification_status: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class LocationResponse(AuditedModel):
    """Model for location API responses."""
    
    id: PyObjectId = Field(..., alias="_id")
    location: Location
    center_id: Optional[PyObjectId] = None
    distance: Optional[float] = None  # For search results
    
    class Config:
        json_encoders = {
            datetime: lambda dt: dt.isoformat() if dt else None,
            PyObjectId: str
        }

class GeoSearchQuery(AuditedModel):
    """Model for geographic search parameters."""
    
    coordinates: Coordinates
    radius: float = Field(..., gt=0, le=100)  # Radius in kilometers
    filters: Optional[Dict[str, Any]] = None
    limit: Optional[int] = Field(default=10, ge=1, le=100)
    
    @field_validator('radius')
    def validate_radius(cls, v: float) -> float:
        """Validate search radius."""
        if v <= 0 or v > 100:
            raise ValueError("Search radius must be between 0 and 100 kilometers")
        return v