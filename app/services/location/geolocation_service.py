from typing import Dict, Any, List, Optional, Tuple
import logging
from datetime import datetime
import math
import json
from geopy import distance
from geopy.geocoders import Nominatim
import aiohttp

from ...core.exceptions import LocationError
from ...database import db_manager
from ...config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class LocationService:
    def __init__(self):
        """Initialize location service with enhanced geocoding capabilities."""
        self.api_key = settings.google_maps_api_key
        if not self.api_key:
            raise LocationError("Google Maps API key is missing")

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
        
        # Cache settings
        self.cache_duration = 86400  # 24 hours
        self.geocoding_cache = {}
        
        logger.info("Location service initialized with enhanced validation")

    async def geocode_address(
        self,
        address: str,
        city: str,
        state: str,
        pin_code: str
    ) -> Dict[str, Any]:
        """Convert address to coordinates with comprehensive validation."""
        try:
            # Generate cache key
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

            if not coordinates:
                raise LocationError("Failed to geocode address")

            # Validate coordinates are within India's boundaries
            if not self._validate_coordinates(coordinates):
                raise LocationError(
                    "Location coordinates fall outside India's boundaries"
                )

            # Verify PIN code accuracy
            if not await self._verify_pin_code_accuracy(
                coordinates,
                pin_code,
                city,
                state
            ):
                raise LocationError("PIN code verification failed")

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
            raise LocationError(f"Failed to geocode address: {str(e)}")

    async def find_nearby_centers(
        self,
        coordinates: Dict[str, float],
        radius_km: float = 50.0
    ) -> List[Dict[str, Any]]:
        """Find ATS centers within specified radius with enhanced accuracy."""
        try:
            if not self._validate_coordinates(coordinates):
                raise LocationError("Invalid search coordinates provided")

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

            if not nearby_centers:
                logger.warning("No nearby centers found")
                return []

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
            raise LocationError(f"Failed to find nearby centers: {str(e)}")

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
            raise LocationError(f"Failed to calculate distance: {str(e)}")

    async def validate_address_components(
        self,
        address: Dict[str, str]
    ) -> Dict[str, bool]:
        """Validate individual address components."""
        try:
            validation_results = {
                "pin_code": self._validate_pin_code(address.get("pin_code", "")),
                "state": self._validate_state(address.get("state", "")),
                "city": await self._validate_city(
                    address.get("city", ""),
                    address.get("state", "")
                )
            }

            return validation_results

        except Exception as e:
            logger.error(f"Address validation error: {str(e)}")
            raise LocationError("Failed to validate address components")

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

    def _validate_pin_code(self, pin_code: str) -> bool:
        """Validate Indian PIN code format."""
        import re
        return bool(re.match(r'^\d{6}$', pin_code))

    async def _validate_city(
        self,
        city: str,
        state: str
    ) -> bool:
        """Validate city exists in given state."""
        try:
            city_data = await db_manager.execute_query(
                collection="cities",
                operation="find_one",
                query={"city": city, "state": state}
            )
            return city_data is not None
        except Exception as e:
            logger.error(f"City validation error: {str(e)}")
            return False

    def _validate_state(self, state: str) -> bool:
        """Validate Indian state name."""
        valid_states = {
            "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar",
            "Chhattisgarh", "Goa", "Gujarat", "Haryana", "Himachal Pradesh",
            "Jharkhand", "Karnataka", "Kerala", "Madhya Pradesh",
            "Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland",
            "Odisha", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu",
            "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand",
            "West Bengal"
        }
        return state in valid_states

    def _get_from_cache(self, key: str) -> Optional[Dict[str, Any]]:
        """Retrieve cached geocoding result if not expired."""
        cached_entry = self.geocoding_cache.get(key)
        if cached_entry and (datetime.utcnow() - cached_entry["timestamp"]).total_seconds() < self.cache_duration:
            return cached_entry["data"]
        return None

    def _store_in_cache(self, key: str, data: Dict[str, Any]) -> None:
        """Store geocoding result in cache with a timestamp."""
        self.geocoding_cache[key] = {
            "data": data,
            "timestamp": datetime.utcnow()
        }

    def _estimate_travel_time(self, distance_km: float) -> str:
        """Estimate travel time based on distance."""
        try:
            # Assume an average speed of 50 km/h
            travel_time_hours = distance_km / 50
            hours = int(travel_time_hours)
            minutes = int((travel_time_hours - hours) * 60)
            return f"{hours}h {minutes}m"
        except Exception as e:
            logger.error(f"Travel time estimation error: {str(e)}")
            return "unavailable"

    async def _log_geocoding_operation(
        self,
        address: str,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        success: bool = True
    ) -> None:
        """Log geocoding operation details."""
        try:
            log_entry = {
                "address": address,
                "result": result,
                "error": error,
                "success": success,
                "timestamp": datetime.utcnow().isoformat()
            }
            await db_manager.execute_query(
                collection="geocoding_logs",
                operation="insert_one",
                query=log_entry
            )
        except Exception as e:
            logger.error(f"Geocoding log error: {str(e)}")

# Initialize location service
location_service = LocationService()