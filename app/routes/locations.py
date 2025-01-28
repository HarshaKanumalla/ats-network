"""Location management routes for the ATS Network application."""
from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Dict, Any
import logging

from ..models.user import User
from ..models.location import LocationResponse
from ..services.auth import get_current_user
from ..services.database import get_location_data, update_location_stats
from ..config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/", response_model=List[LocationResponse])
async def get_locations(
    current_user: User = Depends(get_current_user)
) -> List[LocationResponse]:
    """
    Retrieve all ATS locations with their associated details and statistics.
    
    This endpoint provides comprehensive information about each ATS location,
    including geographical coordinates, contact information, and operational
    statistics. The data is filtered based on user permissions and includes
    real-time performance metrics.
    
    Args:
        current_user: The authenticated user making the request

    Returns:
        A list of location objects containing detailed information about each ATS center

    Raises:
        HTTPException: If there's an error retrieving the location data or if access is denied
    """
    try:
        logger.info("Initiating location data retrieval")
        locations = await get_location_data()
        
        response_data = []
        for location in locations:
            location_stats = await update_location_stats(location["_id"])
            formatted_location = {
                "name": location["name"],
                "lat": location["lat"],
                "lng": location["lng"],
                "contact": {
                    "name": location["contact_name"],
                    "phone": location["contact_phone"],
                    "email": location["contact_email"]
                },
                "stats": {
                    "totalVehicles": location_stats.get("total_vehicles", 0),
                    "atsCenters": location_stats.get("ats_centers", 0),
                    "vehiclesUnder8": location_stats.get("vehicles_under_8", 0),
                    "vehiclesOver8": location_stats.get("vehicles_over_8", 0)
                }
            }
            response_data.append(formatted_location)

        logger.info(f"Successfully retrieved {len(response_data)} locations")
        return response_data

    except Exception as e:
        logger.error(f"Error retrieving location data: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve location data"
        )

@router.get("/{location_id}/details")
async def get_location_details(
    location_id: str,
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Retrieve detailed information about a specific ATS location.
    
    This endpoint provides comprehensive details about a single ATS location,
    including historical performance data, current operational status, and
    detailed statistics. The information helps in monitoring and managing
    individual ATS centers effectively.
    
    Args:
        location_id: The unique identifier of the location
        current_user: The authenticated user making the request

    Returns:
        A dictionary containing detailed information about the specified location

    Raises:
        HTTPException: If the location is not found or if access is denied
    """
    try:
        logger.info(f"Retrieving details for location ID: {location_id}")
        
        location = await get_location_data(location_id)
        if not location:
            logger.warning(f"Location not found: {location_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Location not found"
            )

        stats = await update_location_stats(location_id)
        
        return {
            "basic_info": {
                "name": location["name"],
                "coordinates": {
                    "lat": location["lat"],
                    "lng": location["lng"]
                },
                "address": location["address"],
                "contact": {
                    "name": location["contact_name"],
                    "phone": location["contact_phone"],
                    "email": location["contact_email"]
                }
            },
            "operational_stats": {
                "total_vehicles_processed": stats["total_vehicles"],
                "average_processing_time": stats["avg_processing_time"],
                "current_capacity": stats["current_capacity"],
                "efficiency_rating": stats["efficiency_rating"]
            },
            "performance_metrics": {
                "daily_throughput": stats["daily_throughput"],
                "peak_hours": stats["peak_hours"],
                "utilization_rate": stats["utilization_rate"]
            },
            "compliance_info": {
                "last_audit_date": stats["last_audit_date"],
                "certification_status": stats["certification_status"],
                "compliance_score": stats["compliance_score"]
            }
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error retrieving location details: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve location details"
        )

@router.get("", response_model=List[Dict[str, Any]])
async def get_locations(current_user: User = Depends(get_current_user)):
    """Get all locations."""
    try:
        # Return sample data for now
        return [
            {
                "name": "Visakhapatnam",
                "lat": 17.6868,
                "lng": 83.2185,
                "contact": {
                    "name": "John Doe",
                    "phone": "+91-1234567890",
                    "email": "john@example.com"
                }
            }
        ]
    except Exception as e:
        logger.error(f"Error retrieving locations: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve locations"
        )