# backend/app/api/v1/vehicles.py

from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile
from typing import List, Optional, Dict, Any
import logging
from datetime import datetime
from bson import ObjectId

from ...core.auth.permissions import RolePermission, require_permission
from ...core.security import get_current_user
from ...services.vehicle.service import vehicle_service
from ...services.document.service import document_service
from ...services.s3.service import s3_service
from ...services.notification.service import notification_service
from ...models.vehicle import (
    VehicleCreate,
    VehicleUpdate,
    VehicleResponse,
    VehicleFilter,
    DocumentVerification
)
from ...config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter()

@router.post("", response_model=VehicleResponse)
async def register_vehicle(
    vehicle_data: VehicleCreate,
    documents: List[UploadFile] = File(...),
    current_user=Depends(get_current_user),
    _=Depends(require_permission(RolePermission.REGISTER_VEHICLES))
) -> VehicleResponse:
    """Register a new vehicle with document verification."""
    try:
        # Validate registration number format and uniqueness
        if not vehicle_service.validate_registration_number(vehicle_data.registration_number):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid vehicle registration number format"
            )

        if await vehicle_service.get_vehicle_by_registration(vehicle_data.registration_number):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Vehicle already registered"
            )

        # Process and validate documents
        document_verifications = await document_service.process_vehicle_documents(
            registration_number=vehicle_data.registration_number,
            documents=documents,
            user_id=str(current_user.id)
        )

        # Create vehicle record
        vehicle = await vehicle_service.create_vehicle(
            vehicle_data=vehicle_data,
            document_verifications=document_verifications,
            created_by=str(current_user.id)
        )

        # Send notifications
        await notification_service.notify_vehicle_registration(
            vehicle_id=str(vehicle.id),
            registration_number=vehicle.registration_number,
            owner_email=vehicle_data.owner_info.email
        )

        logger.info(f"Vehicle registered successfully: {vehicle.registration_number[:5]}***")
        return VehicleResponse(
            status="success",
            message="Vehicle registered successfully",
            data=vehicle
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Vehicle registration error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to register vehicle"
        )

@router.get("/search", response_model=List[VehicleResponse])
async def search_vehicles(
    filters: VehicleFilter = Depends(),
    current_user=Depends(get_current_user),
    _=Depends(require_permission(RolePermission.VIEW_VEHICLES))
) -> List[VehicleResponse]:
    """Search vehicles based on various criteria with role-based filtering."""
    try:
        vehicles = await vehicle_service.search_vehicles(
            filters=filters,
            user_role=current_user.role,
            center_id=current_user.center_id
        )

        logger.info(f"Vehicles retrieved successfully by user ID: {current_user.id}")
        return [
            VehicleResponse(
                status="success",
                message="Vehicle retrieved successfully",
                data=vehicle
            ) for vehicle in vehicles
        ]

    except Exception as e:
        logger.error(f"Vehicle search error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to search vehicles"
        )

@router.get("/{vehicle_id}", response_model=VehicleResponse)
async def get_vehicle(
    vehicle_id: str,
    current_user=Depends(get_current_user),
    _=Depends(require_permission(RolePermission.VIEW_VEHICLES))
) -> VehicleResponse:
    """Get detailed vehicle information including test history."""
    try:
        vehicle = await vehicle_service.get_vehicle_details(
            vehicle_id=vehicle_id,
            user_role=current_user.role,
            center_id=current_user.center_id
        )

        if not vehicle:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vehicle not found"
            )

        logger.info(f"Vehicle retrieved successfully: {vehicle_id[:5]}***")
        return VehicleResponse(
            status="success",
            message="Vehicle retrieved successfully",
            data=vehicle
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Vehicle retrieval error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve vehicle"
        )

@router.put("/{vehicle_id}", response_model=VehicleResponse)
async def update_vehicle(
    vehicle_id: str,
    updates: VehicleUpdate,
    current_user=Depends(get_current_user),
    _=Depends(require_permission(RolePermission.MANAGE_VEHICLES))
) -> VehicleResponse:
    """Update vehicle information."""
    try:
        # Validate registration number if provided
        if updates.registration_number:
            if not vehicle_service.validate_registration_number(updates.registration_number):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid vehicle registration number format"
                )

        updated_vehicle = await vehicle_service.update_vehicle(
            vehicle_id=vehicle_id,
            updates=updates,
            updated_by=str(current_user.id)
        )

        logger.info(f"Vehicle updated successfully: {vehicle_id[:5]}***")
        return VehicleResponse(
            status="success",
            message="Vehicle updated successfully",
            data=updated_vehicle
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Vehicle update error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update vehicle"
        )

@router.post("/{vehicle_id}/documents", response_model=VehicleResponse)
async def update_vehicle_documents(
    vehicle_id: str,
    document_type: str,
    document: UploadFile = File(...),
    current_user=Depends(get_current_user),
    _=Depends(require_permission(RolePermission.MANAGE_VEHICLES))
) -> VehicleResponse:
    """Update vehicle documentation."""
    try:
        # Validate document type
        if not document_service.validate_document_type(document_type):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid document type"
            )

        # Process document
        document_verification = await document_service.process_document(
            vehicle_id=vehicle_id,
            document_type=document_type,
            document=document,
            user_id=str(current_user.id)
        )

        # Update vehicle record
        updated_vehicle = await vehicle_service.update_document(
            vehicle_id=vehicle_id,
            document_type=document_type,
            document_verification=document_verification,
            updated_by=str(current_user.id)
        )

        logger.info(f"Document updated successfully for vehicle ID: {vehicle_id[:5]}***")
        return VehicleResponse(
            status="success",
            message="Document updated successfully",
            data=updated_vehicle
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Document update error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update document"
        )

@router.get("/{vehicle_id}/test-history", response_model=List[Dict[str, Any]])
async def get_vehicle_test_history(
    vehicle_id: str,
    current_user=Depends(get_current_user),
    _=Depends(require_permission(RolePermission.VIEW_TEST_HISTORY))
) -> List[Dict[str, Any]]:
    """Get complete test history for a vehicle."""
    try:
        history = await vehicle_service.get_test_history(
            vehicle_id=vehicle_id,
            user_role=current_user.role,
            center_id=current_user.center_id
        )

        logger.info(f"Test history retrieved successfully for vehicle ID: {vehicle_id[:5]}***")
        return history

    except Exception as e:
        logger.error(f"Test history retrieval error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve test history"
        )

@router.get("/statistics/center/{center_id}", response_model=Dict[str, Any])
async def get_center_vehicle_statistics(
    center_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user=Depends(get_current_user),
    _=Depends(require_permission(RolePermission.VIEW_STATISTICS))
) -> Dict[str, Any]:
    """Get vehicle statistics for a specific center."""
    try:
        # Verify center access
        if not await vehicle_service.can_access_center_statistics(
            user=current_user,
            center_id=center_id
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to view these statistics"
            )

        stats = await vehicle_service.get_center_statistics(
            center_id=center_id,
            start_date=start_date,
            end_date=end_date
        )

        logger.info(f"Statistics retrieved successfully for center ID: {center_id}")
        return {
            "status": "success",
            "message": "Statistics retrieved successfully",
            "data": stats
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Statistics retrieval error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve statistics"
        )

@router.post("/{vehicle_id}/verify-documents", response_model=VehicleResponse)
async def verify_vehicle_documents(
    vehicle_id: str,
    document_type: str,
    verification_status: str,
    verification_notes: Optional[str] = None,
    current_user=Depends(get_current_user),
    _=Depends(require_permission(RolePermission.VERIFY_DOCUMENTS))
) -> VehicleResponse:
    """Verify vehicle documents."""
    try:
        updated_vehicle = await vehicle_service.verify_document(
            vehicle_id=vehicle_id,
            document_type=document_type,
            verification_status=verification_status,
            verification_notes=verification_notes,
            verified_by=str(current_user.id)
        )

        # Send notification if verification failed
        if verification_status == "rejected":
            await notification_service.notify_document_verification(
                vehicle_id=vehicle_id,
                document_type=document_type,
                status="rejected",
                notes=verification_notes
            )

        logger.info(f"Document verification updated successfully for vehicle ID: {vehicle_id[:5]}***")
        return VehicleResponse(
            status="success",
            message="Document verification updated successfully",
            data=updated_vehicle
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Document verification error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to verify document"
        )