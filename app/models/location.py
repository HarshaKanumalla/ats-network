# backend/app/models/location.py
from typing import Dict, Optional
from pydantic import BaseModel, Field
from .user import PyObjectId

class LocationBase(BaseModel):
    name: str
    lat: float
    lng: float
    contact_name: str
    contact_phone: str
    contact_email: str

class LocationCreate(LocationBase):
    pass

class Location(LocationBase):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    
    class Config:
        from_attributes = True
        populate_by_name = True
        arbitrary_types_allowed = True

class LocationResponse(BaseModel):
    name: str
    lat: float
    lng: float
    contact: Dict[str, str]
    stats: Dict[str, int]

    class Config:
        from_attributes = True
        json_schema_extra = {
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