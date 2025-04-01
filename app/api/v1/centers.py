# backend/app/api/v1/centers.py

from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile
from typing import List, Optional, Dict, Any
import logging
from datetime import datetime
from bson import ObjectId

from ...core.auth.permissions import (
    RolePermission,
    require_permission,
    check_center_access
)
from ...core.security import get_current_user
from ...services.center.service import center_service
from ...services.location.service import location_service
from ...services.s3.service import s3_service
from ...services.notification.service import notification_service
from ...models.center import (
    CenterCreate,
    CenterUpdate,
    CenterResponse,
    CenterStatistics,
    CenterEquipment
)
from ...config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter()

@router.post("", response_model=CenterResponse)
async def create_center(
    center_data: CenterCreate,
    documents: List[UploadFile] = File(...),
    current_user=Depends(get_current_user),
    _=Depends(require_permission(RolePermission.MANAGE_CENTERS))
) -> CenterResponse:
    """Create a new ATS center with proper validation and location handling."""
    try:
        # Validate center code uniqueness
        if await center_service.get_center_by_code(center_data.center_code):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Center code already exists"
            )

        # Geocode and validate address
        location_data = await location_service.geocode_address(
            address=center_data.address,
            city=center_data.city,
            state=center_data.state,
            pin_code=center_data.pin_code
        )

        if not location_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid address or location"
            )

        # Process and store documents
        document_urls = await s3_service.upload_documents(
            files=documents,
            folder=f"centers/{center_data.center_code}/documents",
            metadata={
                "center_code": center_data.center_code,
                "uploaded_by": str(current_user.id)
            }
        )

        # Create center record
        center = await center_service.create_center(
            center_data=center_data,
            location=location_data,
            document_urls=document_urls,
            created_by=str(current_user.id)
        )

        # Notify relevant parties
        await notification_service.notify_center_creation(center.id)

        logger.info(f"Created ATS center: {center.center_code}")
        return CenterResponse(
            status="success",
            message="ATS center created successfully",
            data=center
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Center creation error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create center"
        )

@router.get("", response_model=List[CenterResponse])
async def get_centers(
    state: Optional[str] = None,
    city: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    radius: Optional[float] = None,
    status: Optional[str] = None,
    current_user=Depends(get_current_user)
) -> List[CenterResponse]:
    """Get centers based on various search criteria with role-based filtering."""
    try:
        # Handle location-based search
        if all([latitude, longitude, radius]):
            centers = await center_service.search_centers_by_location(
                latitude=latitude,
                longitude=longitude,
                radius_km=radius
            )
        # Handle regional search
        else:
            centers = await center_service.search_centers_by_region(
                state=state,
                city=city,
                status=status
            )

        # Apply role-based filtering
        filtered_centers = await center_service.filter_centers_by_role(
            centers=centers,
            user=current_user
        )

        # Add distance if location search
        if latitude and longitude:
            for center in filtered_centers:
                center.distance = location_service.calculate_distance(
                    latitude, longitude,
                    center.location.latitude,
                    center.location.longitude
                )

        return [
            CenterResponse(
                status="success",
                message="Center retrieved successfully",
                data=center
            ) for center in filtered_centers
        ]

    except Exception as e:
        logger.error(f"Center retrieval error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve centers"
        )

@router.get("/{center_id}", response_model=CenterResponse)
async def get_center(
    center_id: str,
    current_user=Depends(get_current_user)
) -> CenterResponse:
    """Get detailed center information with role-based access control."""
    try:
        # Check access permission
        if not await check_center_access(current_user, center_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to access this center"
            )

        center = await center_service.get_center_details(center_id)
        if not center:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Center not found"
            )

        return CenterResponse(
            status="success",
            message="Center retrieved successfully",
            data=center
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Center retrieval error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve center"
        )

@router.put("/{center_id}", response_model=CenterResponse)
async def update_center(
    center_id: str,
    updates: CenterUpdate,
    current_user=Depends(get_current_user),
    _=Depends(require_permission(RolePermission.MANAGE_CENTERS))
) -> CenterResponse:
    """Update center information with proper validation."""
    try:
        # Verify access permission
        if not await check_center_access(current_user, center_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to update this center"
            )

        # Handle location update if address changed
        if updates.address or updates.city or updates.state or updates.pin_code:
            location_data = await location_service.geocode_address(
                address=updates.address or "",
                city=updates.city or "",
                state=updates.state or "",
                pin_code=updates.pin_code or ""
            )
            updates.location = location_data

        updated_center = await center_service.update_center(
            center_id=center_id,
            updates=updates,
            updated_by=str(current_user.id)
        )

        logger.info(f"Updated center: {center_id}")
        return CenterResponse(
            status="success",
            message="Center updated successfully",
            data=updated_center
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Center update error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update center"
        )

@router.post("/{center_id}/equipment", response_model=CenterResponse)
async def update_equipment(
    center_id: str,
    equipment: CenterEquipment,
    current_user=Depends(get_current_user),
    _=Depends(require_permission(RolePermission.MANAGE_CENTER_EQUIPMENT))
) -> CenterResponse:
    """Update center equipment information."""
    try:
        # Verify access permission
        if not await check_center_access(current_user, center_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to manage this center's equipment"
            )

        updated_center = await center_service.update_equipment(
            center_id=center_id,
            equipment=equipment,
            updated_by=str(current_user.id)
        )

        return CenterResponse(
            status="success",
            message="Equipment updated successfully",
            data=updated_center
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Equipment update error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update equipment"
        )

@router.get("/{center_id}/statistics", response_model=CenterStatistics)
async def get_center_statistics(
    center_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user=Depends(get_current_user),
    _=Depends(require_permission(RolePermission.VIEW_CENTER_STATS))
) -> CenterStatistics:
    """Get comprehensive center statistics."""
    try:
        # Verify access permission
        if not await check_center_access(current_user, center_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to view these statistics"
            )

        stats = await center_service.get_center_statistics(
            center_id=center_id,
            start_date=start_date,
            end_date=end_date
        )

        return CenterStatistics(
            status="success",
            message="Statistics retrieved successfully",
            data=stats
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Statistics retrieval error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve statistics"
        )