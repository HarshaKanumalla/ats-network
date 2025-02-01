# backend/app/utils/location_utils.py

from typing import Dict, Tuple, Optional
import math

class LocationUtils:
    """Utility functions for location handling."""
    
    EARTH_RADIUS_KM = 6371

    @staticmethod
    def validate_coordinates(lat: float, lng: float) -> bool:
        """Validate geographical coordinates."""
        return -90 <= lat <= 90 and -180 <= lng <= 180

    @staticmethod
    def calculate_distance(
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float
    ) -> float:
        """Calculate distance between two points in kilometers."""
        # Convert decimal degrees to radians
        lat1, lon1 = math.radians(lat1), math.radians(lon1)
        lat2, lon2 = math.radians(lat2), math.radians(lon2)
        
        # Haversine formula
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        
        return LocationUtils.EARTH_RADIUS_KM * c