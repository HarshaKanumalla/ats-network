from typing import Tuple, Optional
import math

class LocationUtils:
    """Utility functions for location handling."""
    
    EARTH_RADIUS_KM = 6371

    @staticmethod
    def validate_coordinates(lat: Optional[float], lng: Optional[float]) -> bool:
        """
        Validate geographical coordinates.
        
        Args:
            lat (Optional[float]): Latitude value.
            lng (Optional[float]): Longitude value.
        
        Returns:
            bool: True if the coordinates are valid, False otherwise.
        """
        if lat is None or lng is None:
            return False
        if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
            return False
        return -90 <= lat <= 90 and -180 <= lng <= 180

    @staticmethod
    def calculate_distance(
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float
    ) -> Optional[float]:
        """
        Calculate the distance between two points in kilometers using the Haversine formula.
        
        Args:
            lat1 (float): Latitude of the first point.
            lon1 (float): Longitude of the first point.
            lat2 (float): Latitude of the second point.
            lon2 (float): Longitude of the second point.
        
        Returns:
            Optional[float]: The distance in kilometers, or None if the coordinates are invalid.
        """
        if not (LocationUtils.validate_coordinates(lat1, lon1) and 
                LocationUtils.validate_coordinates(lat2, lon2)):
            return None
        
        # Convert decimal degrees to radians
        lat1, lon1 = math.radians(lat1), math.radians(lon1)
        lat2, lon2 = math.radians(lat2), math.radians(lon2)
        
        # Haversine formula
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat / 2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2)**2
        c = 2 * math.asin(math.sqrt(a))
        
        return LocationUtils.EARTH_RADIUS_KM * c

    @staticmethod
    def calculate_midpoint(
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float
    ) -> Optional[Tuple[float, float]]:
        """
        Calculate the midpoint between two geographical points.
        
        Args:
            lat1 (float): Latitude of the first point.
            lon1 (float): Longitude of the first point.
            lat2 (float): Latitude of the second point.
            lon2 (float): Longitude of the second point.
        
        Returns:
            Optional[Tuple[float, float]]: The latitude and longitude of the midpoint, or None if the coordinates are invalid.
        """
        if not (LocationUtils.validate_coordinates(lat1, lon1) and 
                LocationUtils.validate_coordinates(lat2, lon2)):
            return None
        
        # Convert decimal degrees to radians
        lat1, lon1 = math.radians(lat1), math.radians(lon1)
        lat2, lon2 = math.radians(lat2), math.radians(lon2)
        
        # Calculate midpoint
        bx = math.cos(lat2) * math.cos(lon2 - lon1)
        by = math.cos(lat2) * math.sin(lon2 - lon1)
        mid_lat = math.atan2(
            math.sin(lat1) + math.sin(lat2),
            math.sqrt((math.cos(lat1) + bx)**2 + by**2)
        )
        mid_lon = lon1 + math.atan2(by, math.cos(lat1) + bx)
        
        # Convert radians back to degrees
        return math.degrees(mid_lat), math.degrees(mid_lon)

    @staticmethod
    def is_within_radius(
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float,
        radius_km: float
    ) -> bool:
        """
        Check if a point is within a certain radius of another point.
        
        Args:
            lat1 (float): Latitude of the first point.
            lon1 (float): Longitude of the first point.
            lat2 (float): Latitude of the second point.
            lon2 (float): Longitude of the second point.
            radius_km (float): The radius in kilometers.
        
        Returns:
            bool: True if the second point is within the radius of the first point, False otherwise.
        """
        distance = LocationUtils.calculate_distance(lat1, lon1, lat2, lon2)
        if distance is None:
            return False
        return distance <= radius_km