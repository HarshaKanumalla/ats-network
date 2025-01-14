# backend/app/routes/locations.py
from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
import logging
from ..services.auth import get_current_user
from ..models.user import User
from motor.motor_asyncio import AsyncIOMotorClient
from ..config import get_settings

# Set up logging
logger = logging.getLogger(__name__)

# Initialize router with prefix
router = APIRouter(prefix="/api")

# Initialize database connection
settings = get_settings()
client = AsyncIOMotorClient(settings.mongodb_url)
db = client[settings.database_name]

@router.get("/locations")  # Changed from "/api/locations"
async def get_locations(current_user: User = Depends(get_current_user)):
    """Get all ATS locations with their details."""
    try:
        locations = await db.locations.find().to_list(None)
        logger.info(f"Retrieved {len(locations)} locations")
        
        # Format the response data
        response_data = []
        for location in locations:
            location_stats = await db.ats_stats.find_one({"location_id": location["_id"]})
            response_data.append({
                "name": location["name"],
                "lat": location["lat"],
                "lng": location["lng"],
                "contact": {
                    "name": location["contact_name"],
                    "phone": location["contact_phone"],
                    "email": location["contact_email"]
                },
                "stats": {
                    "totalVehicles": location_stats["total_vehicles"] if location_stats else 0,
                    "atsCenters": location_stats["ats_centers"] if location_stats else 0,
                    "vehiclesUnder8": location_stats["vehicles_under_8"] if location_stats else 0,
                    "vehiclesOver8": location_stats["vehicles_over_8"] if location_stats else 0
                }
            })
        return response_data
    except Exception as e:
        logger.error(f"Error fetching locations: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch locations: {str(e)}"
        )