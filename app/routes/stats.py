"""Statistics routes for centralized analytics and reporting."""
from fastapi import APIRouter, Depends, HTTPException, status
from typing import Dict, Any
import logging

from ..models.user import User
from ..services.auth import get_current_user
from ..services.database import get_overall_statistics

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/overview")
async def get_overall_statistics(
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Retrieve comprehensive network-wide statistics.
    
    This endpoint aggregates data across all ATS centers to provide high-level
    insights into the network's performance, including testing volumes, vehicle
    categories, and operational metrics. The statistics help in strategic
    decision-making and performance monitoring.
    """
    try:
        logger.info("Retrieving network-wide statistics")
        stats = await get_overall_stats()
        
        return {
            "summary": {
                "total_vehicles": stats.get("total_vehicles", 0),
                "ats_centers": stats.get("ats_centers", 0),
                "vehicles_under_8": stats.get("vehicles_under_8", 0),
                "vehicles_over_8": stats.get("vehicles_over_8", 0)
            },
            "performance_metrics": {
                "average_processing_time": stats.get("avg_processing_time"),
                "network_utilization": stats.get("network_utilization"),
                "efficiency_score": stats.get("efficiency_score")
            },
            "compliance_metrics": {
                "compliance_rate": stats.get("compliance_rate"),
                "certification_status": stats.get("certification_status")
            }
        }

    except Exception as e:
        logger.error(f"Error retrieving overall statistics: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve statistics"
        )


@router.get("", response_model=Dict[str, Any])
async def get_stats(current_user: User = Depends(get_current_user)):
    """Get system statistics."""
    try:
        # Return sample data for now
        return {
            "totalVehicles": 150,
            "atsCenters": 5,
            "vehiclesUnder8": 90,
            "vehiclesOver8": 60
        }
    except Exception as e:
        logger.error(f"Error retrieving stats: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve statistics"
        )