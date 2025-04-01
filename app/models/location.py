"""Location and geographical data models with enhanced validation."""
from typing import Optional, List, Dict, Any
from pydantic import Field, validator, field_validator
from datetime import datetime
from math import radians, sin, cos, asin, sqrt
from zoneinfo import ZoneInfo, available_timezones
import logging

from .common import AuditedModel, PyObjectId
from ..config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

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
    
    VALID_STATES = [
        "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", 
        "Chhattisgarh", "Goa", "Gujarat", "Haryana", "Himachal Pradesh",
        "Jharkhand", "Karnataka", "Kerala", "Madhya Pradesh", "Maharashtra",
        "Manipur", "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Punjab",
        "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura",
        "Uttar Pradesh", "Uttarakhand", "West Bengal"
    ]
    
    street: str = Field(..., min_length=5, max_length=200)
    area: Optional[str] = Field(default=None, max_length=100)
    landmark: Optional[str] = Field(default=None, max_length=100)
    city: str = Field(..., min_length=2, max_length=100)
    district: str = Field(..., min_length=2, max_length=100)
    state: str = Field(..., min_length=2, max_length=100)
    pin_code: str = Field(..., pattern=r'^\d{6}$')
    
    @field_validator('state')
    def validate_state(cls, v: str) -> str:
        state = v.title()
        if state not in cls.VALID_STATES:
            raise ValueError(f"Invalid state. Must be one of: {cls.VALID_STATES}")
        return state
    
    @field_validator('city', 'district')
    def validate_city_district(cls, v: str) -> str:
        if not v.replace(' ', '').isalpha():
            raise ValueError("City/District should contain only letters and spaces")
        return v.title()
    
    @field_validator('pin_code')
    def validate_pin_code(cls, v: str) -> str:
        """Validate PIN code format and existence."""
        if not v.isdigit() or len(v) != 6:
            raise ValueError("Invalid PIN code format")
        return v

class Location(AuditedModel):
    """Comprehensive location model with address and coordinates."""
    
    VALID_STATUSES = ['pending', 'verified', 'rejected', 'inactive']
    VALID_TYPES = ['business', 'residential', 'industrial', 'commercial']
    
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
    
    @field_validator('verification_status')
    def validate_status(cls, v: str) -> str:
        if v not in cls.VALID_STATUSES:
            raise ValueError(f"Invalid status. Must be one of: {cls.VALID_STATUSES}")
        return v
        
    @field_validator('location_type')
    def validate_type(cls, v: str) -> str:
        if v not in cls.VALID_TYPES:
            raise ValueError(f"Invalid type. Must be one of: {cls.VALID_TYPES}")
        return v
    
    @field_validator('timezone')
    def validate_timezone(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in available_timezones():
            raise ValueError(f"Invalid timezone: {v}")
        return v
    
    @field_validator('administrative_area')
    def validate_administrative_area(cls, v: Optional[Dict[str, str]]) -> Optional[Dict[str, str]]:
        if v is not None:
            required_keys = {'level1', 'level2', 'level3'}
            if not all(key in v for key in required_keys):
                raise ValueError("Administrative area must contain all required levels")
            if not all(isinstance(v[key], str) for key in v):
                raise ValueError("Administrative area values must be strings")
        return v
    
    def calculate_distance(self, other_coordinates: Coordinates) -> float:
        """Calculate distance to another location using Haversine formula."""
        lat1, lon1 = map(radians, [self.coordinates.latitude, self.coordinates.longitude])
        lat2, lon2 = map(radians, [other_coordinates.latitude, other_coordinates.longitude])
        
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * asin(sqrt(a))
        r = 6371  # Earth's radius in kilometers
        
        return round(c * r, 2)
    
    def update_verification(self, status: str, verified_by: PyObjectId) -> None:
        """Update verification status with logging."""
        try:
            old_status = self.verification_status
            self.verification_status = status
            self.verified_by = verified_by
            self.verified_at = datetime.utcnow()
            logger.info(
                f"Location verification updated: {old_status} -> {status} "
                f"by {verified_by}"
            )
        except Exception as e:
            logger.error(f"Failed to update verification: {str(e)}")
            raise ValueError(f"Verification update failed: {str(e)}")
    
    class Config:
        json_encoders = {
            datetime: lambda dt: dt.isoformat() if dt else None,
            PyObjectId: str
        }

class LocationCreate(AuditedModel):
    """Model for creating a new location record."""
    
    address: Address
    coordinates: Optional[Coordinates] = None
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
    
    def format_distance(self) -> str:
        """Format distance for display."""
        if self.distance is None:
            return "N/A"
        if self.distance < 1:
            return f"{int(self.distance * 1000)}m"
        return f"{self.distance:.1f}km"
    
    def get_summary(self) -> Dict[str, Any]:
        """Get location summary."""
        return {
            "id": str(self.id),
            "address": self.location.address.formatted_address,
            "coordinates": {
                "lat": self.location.coordinates.latitude,
                "lng": self.location.coordinates.longitude
            },
            "distance": self.format_distance(),
            "verified": self.location.verification_status == "verified"
        }
    
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
    
    def generate_geo_bounds(self) -> Dict[str, float]:
        """Generate bounding box for optimized search."""
        km_per_lat = 111.0  # Approximate kilometers per degree latitude
        km_per_lon = cos(radians(self.coordinates.latitude)) * 111.0
        
        lat_delta = self.radius / km_per_lat
        lon_delta = self.radius / km_per_lon
        
        return {
            "min_lat": self.coordinates.latitude - lat_delta,
            "max_lat": self.coordinates.latitude + lat_delta,
            "min_lon": self.coordinates.longitude - lon_delta,
            "max_lon": self.coordinates.longitude + lon_delta
        }