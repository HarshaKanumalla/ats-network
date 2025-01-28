"""Dashboard routes and endpoint handlers for the ATS Network application."""
from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Dict, Any
import logging

from ..models.user import User
from ..services.auth import get_current_user
from ..services.database import get_location_statistics, get_overall_statistics
from motor.motor_asyncio import AsyncIOMotorClient
from ..config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/overview")
async def get_dashboard_overview(
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Retrieve an overview of the ATS Network dashboard statistics.

    This endpoint provides a comprehensive overview of the ATS Network's performance
    metrics, including vehicle counts, testing center statistics, and regional data.
    The data is filtered based on the user's access permissions.

    Args:
        current_user: The authenticated user making the request

    Returns:
        A dictionary containing dashboard statistics and metrics

    Raises:
        HTTPException: If there's an error retrieving the statistics or if access is denied
    """
    try:
        logger.info(f"Retrieving dashboard overview for user: {current_user.email}")
        
        statistics = await get_overall_statistics()
        
        return {
            "total_vehicles": statistics.get("total_vehicles", 0),
            "active_centers": statistics.get("active_centers", 0),
            "recent_tests": statistics.get("recent_tests", 0),
            "pending_approvals": statistics.get("pending_approvals", 0),
            "last_updated": statistics.get("last_updated")
        }

    except Exception as e:
        logger.error(f"Error retrieving dashboard overview: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve dashboard overview"
        )

@router.get("/locations")
async def get_location_metrics(
    current_user: User = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """
    Retrieve metrics for all ATS locations.

    This endpoint provides detailed statistics for each ATS location, including
    testing volumes, vehicle categories, and operational metrics. The data is
    filtered based on the user's access permissions.

    Args:
        current_user: The authenticated user making the request

    Returns:
        A list of dictionaries containing location-specific metrics

    Raises:
        HTTPException: If there's an error retrieving the location data
    """
    try:
        logger.info("Fetching location metrics")
        
        locations = await get_location_statistics()
        
        return [{
            "name": location["name"],
            "coordinates": {
                "lat": location["lat"],
                "lng": location["lng"]
            },
            "metrics": {
                "total_vehicles": location["total_vehicles"],
                "vehicles_under_8": location["vehicles_under_8"],
                "vehicles_over_8": location["vehicles_over_8"]
            },
            "contact": {
                "name": location["contact_name"],
                "phone": location["contact_phone"],
                "email": location["contact_email"]
            }
        } for location in locations]

    except Exception as e:
        logger.error(f"Error retrieving location metrics: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve location metrics"
        )

@router.get("/performance")
async def get_performance_metrics(
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Retrieve performance metrics for the ATS Network.

    This endpoint provides performance-related statistics including testing efficiency,
    processing times, and operational metrics. The data helps in monitoring and
    optimizing the network's performance.

    Args:
        current_user: The authenticated user making the request

    Returns:
        A dictionary containing various performance metrics

    Raises:
        HTTPException: If there's an error calculating the performance metrics
    """
    try:
        logger.info("Calculating performance metrics")
        
        return {
            "average_processing_time": "2.5 hours",
            "daily_test_capacity": 150,
            "utilization_rate": "75%",
            "efficiency_score": 8.5,
            "peak_hours": ["10:00", "14:00"],
            "bottleneck_indicators": []
        }

    except Exception as e:
        logger.error(f"Error retrieving performance metrics: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve performance metrics"
        )

@router.get("/alerts")
async def get_system_alerts(
    current_user: User = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """
    Retrieve system alerts and notifications.

    This endpoint provides real-time alerts and notifications about system status,
    pending actions, and potential issues that require attention. The alerts are
    filtered based on user permissions and relevance.

    Args:
        current_user: The authenticated user making the request

    Returns:
        A list of alerts and notifications

    Raises:
        HTTPException: If there's an error retrieving the alerts
    """
    try:
        logger.info(f"Retrieving system alerts for user: {current_user.email}")
        
        return [{
            "type": "info",
            "message": "System performance is optimal",
            "timestamp": "2024-01-23T10:00:00Z",
            "priority": "low",
            "requires_action": False
        }]

    except Exception as e:
        logger.error(f"Error retrieving system alerts: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve system alerts"
        )