# backend/app/routes/dashboard.py

from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Dict
import logging
from ..services.auth import get_current_user
from ..models.user import User
from motor.motor_asyncio import AsyncIOMotorClient
from ..config import get_settings

# Set up logging
logger = logging.getLogger(__name__)

# Initialize router with API prefix
router = APIRouter(prefix="/api")

# Get settings and initialize database connection
settings = get_settings()
client = AsyncIOMotorClient(settings.mongodb_url)
db = client[settings.database_name]

@router.get("/locations")
async def get_locations(current_user: User = Depends(get_current_user)):
    """Get all ATS locations with their details and associated statistics."""
    try:
        logger.info("Fetching locations with associated statistics")
        pipeline = [
            {
                "$lookup": {
                    "from": "ats_stats",
                    "localField": "_id",
                    "foreignField": "location_id",
                    "as": "stats"
                }
            },
            {
                "$project": {
                    "name": 1,
                    "lat": 1,
                    "lng": 1,
                    "contact": {
                        "name": "$contact_name",
                        "phone": "$contact_phone",
                        "email": "$contact_email"
                    },
                    "stats": {
                        "$cond": {
                            "if": {"$gt": [{"$size": "$stats"}, 0]},
                            "then": {
                                "totalVehicles": {"$first": "$stats.total_vehicles"},
                                "atsCenters": {"$first": "$stats.ats_centers"},
                                "vehiclesUnder8": {"$first": "$stats.vehicles_under_8"},
                                "vehiclesOver8": {"$first": "$stats.vehicles_over_8"}
                            },
                            "else": {
                                "totalVehicles": 0,
                                "atsCenters": 0,
                                "vehiclesUnder8": 0,
                                "vehiclesOver8": 0
                            }
                        }
                    }
                }
            }
        ]
        
        locations = await db.locations.aggregate(pipeline).to_list(None)
        logger.info(f"Successfully retrieved {len(locations)} locations")
        return locations

    except Exception as e:
        logger.error(f"Error fetching locations: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch locations"
        )

@router.get("/stats")
async def get_overall_stats(current_user: User = Depends(get_current_user)):
    """Get aggregated statistics across all locations."""
    try:
        logger.info("Fetching overall statistics")
        pipeline = [
            {
                "$group": {
                    "_id": None,
                    "totalVehicles": {"$sum": "$total_vehicles"},
                    "atsCenters": {"$sum": "$ats_centers"},
                    "vehiclesUnder8": {"$sum": "$vehicles_under_8"},
                    "vehiclesOver8": {"$sum": "$vehicles_over_8"}
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "totalVehicles": 1,
                    "atsCenters": 1,
                    "vehiclesUnder8": 1,
                    "vehiclesOver8": 1
                }
            }
        ]
        
        result = await db.ats_stats.aggregate(pipeline).to_list(None)
        
        if not result:
            logger.info("No statistics found, returning zeros")
            return {
                "totalVehicles": 0,
                "atsCenters": 0,
                "vehiclesUnder8": 0,
                "vehiclesOver8": 0
            }
            
        logger.info("Successfully retrieved overall statistics")
        return result[0]

    except Exception as e:
        logger.error(f"Error fetching statistics: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch statistics"
        )

# For cleanup when the application shuts down
async def cleanup():
    """Close database connections on application shutdown."""
    try:
        client.close()
        logger.info("Database connections closed")
    except Exception as e:
        logger.error(f"Error during cleanup: {str(e)}")