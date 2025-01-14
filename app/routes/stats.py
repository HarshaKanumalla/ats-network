# backend/app/routes/stats.py
from fastapi import APIRouter, Depends, HTTPException, status
from typing import Dict
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

@router.get("/stats")  # Changed from "/api/stats"
async def get_overall_stats(current_user: User = Depends(get_current_user)):
    """Get overall statistics for the dashboard."""
    try:
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
            return {
                "totalVehicles": 0,
                "atsCenters": 0,
                "vehiclesUnder8": 0,
                "vehiclesOver8": 0
            }
            
        return result[0]
    except Exception as e:
        logger.error(f"Error fetching statistics: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch statistics"
        )