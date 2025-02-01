#backend/app/models/location.py

"""Location and geographical data models."""
from typing import Optional, List, Dict, Any, Tuple
from pydantic import Field, field_validator
from datetime import datetime

from .common import AuditedModel, PyObjectId
from ..config import get_settings

settings = get_settings()

class Coordinates(BaseModel):
    """Geographic coordinates model."""
    
    latitude: float = Field(
        ...,
        ge=-90,
        le=90,
        description="Latitude in decimal degrees"
    )
    longitude: float = Field(
        ...,
        ge=-180,
        le=180,
        description="Longitude in decimal degrees"
    )
    
    @field_validator('latitude')
    def validate_latitude(cls, v: float) -> float:
        """Validate latitude is within India's bounds."""
        if not (settings.MAP_BOUNDS['south'] <= v <= settings.MAP_BOUNDS['north']):
            raise ValueError('Latitude outside permitted bounds')
        return v

    @field_validator('longitude')
    def validate_longitude(cls, v: float) -> float:
        """Validate longitude is within India's bounds."""
        if not (settings.MAP_BOUNDS['west'] <= v <= settings.MAP_BOUNDS['east']):
            raise ValueError('Longitude outside permitted bounds')
        return v

class Location(AuditedModel):
    """Location model for ATS centers."""
    
    coordinates: Coordinates = Field(...)
    address: str = Field(..., min_length=5, max_length=200)
    city: str = Field(..., min_length=2, max_length=100)
    district: str = Field(..., min_length=2, max_length=100)
    state: str = Field(..., min_length=2, max_length=100)
    pin_code: str = Field(..., pattern=r'^\d{6}$')
    
    # Optional additional details
    landmark: Optional[str] = None
    area_name: Optional[str] = None
    directions: Optional[str] = None
    
    # Computed fields
    formatted_address: Optional[str] = None
    place_id: Optional[str] = None

class LocationCreate(Location):
    """Model for creating a new location."""
    
    center_id: PyObjectId = Field(...)
    
    @field_validator('coordinates')
    def validate_coordinates(cls, v: Coordinates) -> Coordinates:
        """Additional validation for new locations."""
        return v

class LocationUpdate(Location):
    """Model for updating location information."""
    
    coordinates: Optional[Coordinates] = None
    address: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    state: Optional[str] = None
    pin_code: Optional[str] = None

class LocationInDB(Location):
    """Internal location model with additional fields."""
    
    center_id: PyObjectId
    geocoding_status: str = Field(default="pending")
    last_verified: Optional[datetime] = None
    
    # Geocoding results
    geocoding_results: Dict[str, Any] = Field(default_factory=dict)
    
    # Additional metadata
    timezone: Optional[str] = None
    administrative_area: Optional[Dict[str, str]] = None
    
    class Config:
        json_encoders = {
            datetime: lambda dt: dt.isoformat() if dt else None,
            PyObjectId: str
        }

class LocationResponse(Location):
    """Location response model."""
    
    id: PyObjectId = Field(..., alias="_id")
    center_id: PyObjectId
    geocoding_status: str
    
    class Config:
        json_encoders = {
            datetime: lambda dt: dt.isoformat() if dt else None,
            PyObjectId: str
        }
        
    def dict(self, *args, **kwargs):
        """Customize dictionary representation."""
        d = super().dict(*args, **kwargs)
        # Remove internal fields
        d.pop('geocoding_results', None)
        return d

class GeoSearchQuery(BaseModel):
    """Model for geographic search parameters."""
    
    center: Coordinates
    radius: float = Field(..., gt=0, le=100)  # Radius in kilometers
    limit: Optional[int] = Field(default=10, ge=1, le=100)
    
    class Config:
        json_encoders = {
            PyObjectId: str
        }