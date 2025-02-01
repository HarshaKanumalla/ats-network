# backend/app/services/location/geolocation_service.py

import aiohttp
from typing import Dict, Any, List, Optional, Tuple
import logging
from datetime import datetime
import math
import json
from geopy import distance
from geopy.geocoders import Nominatim

from ...core.exceptions import GeolocationError
from ...database import db_manager
from ...config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class GeolocationService:
    def __init__(self):
        self.api_key = settings.google_maps_api_key
        self.geocoding_base_url = "https://maps.googleapis.com/maps/api/geocode/json"
        
        # Define India's geographical boundaries
        self.boundaries = {
            'north': 35.5,  # Northern boundary (Kashmir)
            'south': 6.5,   # Southern boundary (Kanyakumari)
            'east': 97.5,   # Eastern boundary (Arunachal Pradesh)
            'west': 68.0    # Western boundary (Gujarat)
        }
        
        # Initialize geocoding utilities
        self.nominatim = Nominatim(
            user_agent="ats_network_geocoder",
            timeout=10
        )
        
        # Cache initialization
        self.geocoding_cache = {}
        self.cache_duration = 86400  # 24 hours
        
        logger.info("Geolocation service initialized with enhanced validation")

    async def geocode_address(
        self,
        address: str,
        city: str,
        state: str,
        pin_code: str
    ) -> Dict[str, Any]:
        """Convert address to coordinates with comprehensive validation."""
        try:
            # Generate cache key for address
            cache_key = f"{address}_{city}_{state}_{pin_code}"
            cached_result = self._get_from_cache(cache_key)
            if cached_result:
                return cached_result

            # Format complete address
            full_address = f"{address}, {city}, {state} {pin_code}, India"

            # Primary geocoding using Google Maps API
            coordinates = await self._geocode_with_google(full_address)
            
            # Fallback to Nominatim if Google geocoding fails
            if not coordinates:
                coordinates = await self._geocode_with_nominatim(full_address)

            # Validate coordinates are within India's boundaries
            if not self._validate_coordinates(coordinates):
                raise GeolocationError(
                    "Location coordinates fall outside India's boundaries"
                )

            # Verify PIN code accuracy
            if not await self._verify_pin_code_accuracy(
                coordinates,
                pin_code,
                city,
                state
            ):
                raise GeolocationError("PIN code verification failed")

            # Create comprehensive location data
            location_data = {
                "coordinates": coordinates,
                "formatted_address": full_address,
                "components": {
                    "address": address,
                    "city": city,
                    "state": state,
                    "pin_code": pin_code
                },
                "metadata": {
                    "geocoding_method": "google_maps",
                    "verification_status": "verified",
                    "timestamp": datetime.utcnow().isoformat()
                }
            }

            # Cache the verified result
            self._store_in_cache(cache_key, location_data)

            # Log successful geocoding
            await self._log_geocoding_operation(
                address=full_address,
                result=location_data,
                success=True
            )

            return location_data

        except Exception as e:
            logger.error(f"Geocoding error for address {full_address}: {str(e)}")
            await self._log_geocoding_operation(
                address=full_address,
                error=str(e),
                success=False
            )
            raise GeolocationError(f"Failed to geocode address: {str(e)}")

    async def find_nearby_centers(
        self,
        coordinates: Dict[str, float],
        radius_km: float = 50.0
    ) -> List[Dict[str, Any]]:
        """Find ATS centers within specified radius with enhanced accuracy."""
        try:
            if not self._validate_coordinates(coordinates):
                raise GeolocationError("Invalid search coordinates provided")

            # Perform optimized geospatial query
            nearby_centers = await db_manager.execute_query(
                collection="centers",
                operation="find",
                query={
                    "location.coordinates": {
                        "$geoWithin": {
                            "$centerSphere": [
                                [coordinates["longitude"], coordinates["latitude"]],
                                radius_km / 6371  # Convert km to radians
                            ]
                        }
                    },
                    "status": "active"
                }
            )

            # Calculate exact distances and additional metadata
            for center in nearby_centers:
                center_coords = center["location"]["coordinates"]
                exact_distance = self.calculate_exact_distance(
                    coordinates,
                    {
                        "latitude": center_coords[1],
                        "longitude": center_coords[0]
                    }
                )
                
                center["distance"] = {
                    "value": exact_distance,
                    "unit": "km"
                }
                center["travel_time_estimate"] = self._estimate_travel_time(
                    exact_distance
                )

            # Sort centers by distance
            return sorted(nearby_centers, key=lambda x: x["distance"]["value"])

        except Exception as e:
            logger.error(f"Nearby centers search error: {str(e)}")
            raise GeolocationError(f"Failed to find nearby centers: {str(e)}")

    def calculate_exact_distance(
        self,
        point1: Dict[str, float],
        point2: Dict[str, float]
    ) -> float:
        """Calculate precise distance between two points using Vincenty formula."""
        try:
            coords1 = (point1["latitude"], point1["longitude"])
            coords2 = (point2["latitude"], point2["longitude"])
            
            return round(
                distance.distance(coords1, coords2).kilometers,
                2
            )
        except Exception as e:
            logger.error(f"Distance calculation error: {str(e)}")
            raise GeolocationError(f"Failed to calculate distance: {str(e)}")

    async def _geocode_with_google(
        self,
        address: str
    ) -> Optional[Dict[str, float]]:
        """Geocode address using Google Maps API with error handling."""
        try:
            params = {
                "address": address,
                "key": self.api_key,
                "region": "in",
                "bounds": (
                    f"{self.boundaries['south']},{self.boundaries['west']}|"
                    f"{self.boundaries['north']},{self.boundaries['east']}"
                )
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.geocoding_base_url,
                    params=params
                ) as response:
                    result = await response.json()

                    if result["status"] == "OK":
                        location = result["results"][0]["geometry"]["location"]
                        return {
                            "latitude": location["lat"],
                            "longitude": location["lng"]
                        }

            return None

        except Exception as e:
            logger.error(f"Google geocoding error: {str(e)}")
            return None

    async def _geocode_with_nominatim(
        self,
        address: str
    ) -> Optional[Dict[str, float]]:
        """Fallback geocoding using Nominatim with rate limiting."""
        try:
            location = self.nominatim.geocode(
                address,
                country_codes="in"
            )
            
            if location:
                return {
                    "latitude": location.latitude,
                    "longitude": location.longitude
                }

            return None

        except Exception as e:
            logger.error(f"Nominatim geocoding error: {str(e)}")
            return None

    def _validate_coordinates(
        self,
        coordinates: Dict[str, float]
    ) -> bool:
        """Validate coordinates are within India's boundaries."""
        return (
            self.boundaries["south"] <= coordinates["latitude"] <= self.boundaries["north"]
            and
            self.boundaries["west"] <= coordinates["longitude"] <= self.boundaries["east"]
        )

    async def _verify_pin_code_accuracy(
        self,
        coordinates: Dict[str, float],
        pin_code: str,
        city: str,
        state: str
    ) -> bool:
        """Verify PIN code accuracy against coordinates."""
        try:
            # Reverse geocode to verify location
            params = {
                "latlng": f"{coordinates['latitude']},{coordinates['longitude']}",
                "key": self.api_key
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.geocoding_base_url,
                    params=params
                ) as response:
                    result = await response.json()

                    if result["status"] == "OK":
                        for component in result["results"][0]["address_components"]:
                            if "postal_code" in component["types"]:
                                return component["long_name"] == pin_code

            return False

        except Exception as e:
            logger.error(f"PIN code verification error: {str(e)}")
            return False

    def _estimate_travel_time(self, distance_km: float) -> Dict[str, Any]:
        """Estimate travel time based on distance and traffic conditions."""
        # Average speed assumptions (km/h)
        speeds = {
            "normal": 40,
            "heavy_traffic": 20,
            "light_traffic": 50
        }

        return {
            "normal": round(distance_km / speeds["normal"] * 60),  # minutes
            "heavy_traffic": round(distance_km / speeds["heavy_traffic"] * 60),
            "light_traffic": round(distance_km / speeds["light_traffic"] * 60)
        }

# Initialize geolocation service
geolocation_service = GeolocationService()