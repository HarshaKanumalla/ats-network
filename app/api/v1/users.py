# backend/app/api/v1/users.py

from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile
from typing import List, Optional, Dict, Any
import logging
from datetime import datetime
from bson import ObjectId

from ...core.auth.permissions import RolePermission, require_permission
from ...core.security import get_current_user, get_password_hash
from ...services.user.service import user_service
from ...services.s3.service import s3_service
from ...services.email.service import email_service
from ...services.notification.service import notification_service
from ...models.user import (
    UserUpdate,
    UserResponse,
    AdminUserUpdate,
    RoleUpdate,
    UserFilter
)
from ...config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter()

@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    current_user=Depends(get_current_user)
) -> UserResponse:
    """Get current user's profile information."""
    try:
        user = await user_service.get_user_by_id(str(current_user.id))
        logger.info(f"Profile retrieved successfully for user ID: {current_user.id}")
        return UserResponse(
            status="success",
            message="Profile retrieved successfully",
            data=user
        )
    except Exception as e:
        logger.error(f"Profile retrieval error for user ID {current_user.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve profile"
        )

@router.put("/me", response_model=UserResponse)
async def update_current_user_profile(
    updates: UserUpdate,
    current_user=Depends(get_current_user)
) -> UserResponse:
    """Update current user's profile information."""
    try:
        # Validate email uniqueness
        if updates.email and updates.email != current_user.email:
            if await user_service.get_user_by_email(updates.email):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already registered"
                )

        updated_user = await user_service.update_user_profile(
            user_id=str(current_user.id),
            updates=updates
        )

        logger.info(f"Profile updated successfully for user ID: {current_user.id}")
        return UserResponse(
            status="success",
            message="Profile updated successfully",
            data=updated_user
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Profile update error for user ID {current_user.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update profile"
        )

@router.post("/me/photo", response_model=UserResponse)
async def update_profile_photo(
    photo: UploadFile = File(...),
    current_user=Depends(get_current_user)
) -> UserResponse:
    """Update user's profile photo."""
    try:
        # Validate image
        if not photo.content_type.startswith('image/'):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid file type. Only images are allowed."
            )

        # Upload to S3
        photo_url = await s3_service.upload_document(
            file=photo,
            folder=f"users/{current_user.id}/profile",
            metadata={
                "user_id": str(current_user.id),
                "content_type": photo.content_type
            }
        )

        # Update user profile
        updated_user = await user_service.update_profile_photo(
            user_id=str(current_user.id),
            photo_url=photo_url
        )

        logger.info(f"Profile photo updated successfully for user ID: {current_user.id}")
        return UserResponse(
            status="success",
            message="Profile photo updated successfully",
            data=updated_user
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Profile photo update error for user ID {current_user.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update profile photo"
        )

@router.get("/pending", response_model=List[UserResponse])
async def get_pending_registrations(
    current_user=Depends(get_current_user),
    _=Depends(require_permission(RolePermission.MANAGE_USERS))
) -> List[UserResponse]:
    """Get all pending user registrations."""
    try:
        pending_users = await user_service.get_pending_registrations()
        logger.info(f"Pending registrations retrieved successfully by user ID: {current_user.id}")
        return [
            UserResponse(
                status="success",
                message="User retrieved successfully",
                data=user
            ) for user in pending_users
        ]
    except Exception as e:
        logger.error(f"Pending registrations retrieval error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve pending registrations"
        )

@router.post("/{user_id}/approve", response_model=UserResponse)
async def approve_user(
    user_id: str,
    approval: AdminUserUpdate,
    current_user=Depends(get_current_user),
    _=Depends(require_permission(RolePermission.MANAGE_USERS))
) -> UserResponse:
    """Approve a user registration with role assignment."""
    try:
        # Validate role assignment
        if not user_service.validate_role_assignment(approval.role):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid role assignment"
            )

        # Update user status
        updated_user = await user_service.approve_user(
            user_id=user_id,
            role=approval.role,
            approved_by=str(current_user.id),
            notes=approval.approval_notes
        )

        # Send approval notification
        await email_service.send_registration_approved(
            email=updated_user.email,
            name=updated_user.full_name,
            role=approval.role
        )

        # Create notification
        await notification_service.create_notification(
            user_id=user_id,
            type="registration_approved",
            title="Registration Approved",
            message=f"Your registration has been approved with role: {approval.role}"
        )

        logger.info(f"User approved successfully for user ID: {user_id}")
        return UserResponse(
            status="success",
            message="User approved successfully",
            data=updated_user
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"User approval error for user ID {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to approve user"
        )

@router.post("/{user_id}/reject", response_model=UserResponse)
async def reject_user(
    user_id: str,
    rejection: AdminUserUpdate,
    current_user=Depends(get_current_user),
    _=Depends(require_permission(RolePermission.MANAGE_USERS))
) -> UserResponse:
    """Reject a user registration."""
    try:
        # Update user status
        updated_user = await user_service.reject_user(
            user_id=user_id,
            rejected_by=str(current_user.id),
            reason=rejection.rejection_reason
        )

        # Send rejection notification
        await email_service.send_registration_rejected(
            email=updated_user.email,
            name=updated_user.full_name,
            reason=rejection.rejection_reason
        )

        logger.info(f"User rejected successfully for user ID: {user_id}")
        return UserResponse(
            status="success",
            message="User rejected successfully",
            data=updated_user
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"User rejection error for user ID {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reject user"
        )

@router.put("/{user_id}/role", response_model=UserResponse)
async def update_user_role(
    user_id: str,
    role_update: RoleUpdate,
    current_user=Depends(get_current_user),
    _=Depends(require_permission(RolePermission.MANAGE_ROLES))
) -> UserResponse:
    """Update user's role and permissions."""
    try:
        # Validate role update
        if not user_service.validate_role_assignment(role_update.role):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid role assignment"
            )

        # Update role
        updated_user = await user_service.update_user_role(
            user_id=user_id,
            role=role_update.role,
            updated_by=str(current_user.id)
        )

        # Send role update notification
        await email_service.send_role_update(
            email=updated_user.email,
            name=updated_user.full_name,
            new_role=role_update.role
        )

        logger.info(f"User role updated successfully for user ID: {user_id}")
        return UserResponse(
            status="success",
            message="User role updated successfully",
            data=updated_user
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Role update error for user ID {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update user role"
        )

@router.get("/", response_model=List[UserResponse])
async def get_users(
    filters: UserFilter = Depends(),
    current_user=Depends(get_current_user),
    _=Depends(require_permission(RolePermission.VIEW_USERS))
) -> List[UserResponse]:
    """Get users based on filters with role-based access control."""
    try:
        # Apply role-based filtering
        users = await user_service.get_users_by_role(
            role=current_user.role,
            filters=filters
        )

        logger.info(f"Users retrieved successfully by user ID: {current_user.id}")
        return [
            UserResponse(
                status="success",
                message="User retrieved successfully",
                data=user
            ) for user in users
        ]

    except Exception as e:
        logger.error(f"User retrieval error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve users"
        )

@router.put("/{user_id}/status", response_model=UserResponse)
async def update_user_status(
    user_id: str,
    status: str,
    current_user=Depends(get_current_user),
    _=Depends(require_permission(RolePermission.MANAGE_USERS))
) -> UserResponse:
    """Update user account status."""
    try:
        # Validate status
        if status not in ["active", "inactive", "suspended"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid status value"
            )

        # Update status
        updated_user = await user_service.update_user_status(
            user_id=user_id,
            status=status,
            updated_by=str(current_user.id)
        )

        # Send status update notification
        await notification_service.create_notification(
            user_id=user_id,
            type="status_update",
            title="Account Status Updated",
            message=f"Your account status has been updated to: {status}"
        )

        logger.info(f"User status updated successfully for user ID: {user_id}")
        return UserResponse(
            status="success",
            message="User status updated successfully",
            data=updated_user
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Status update error for user ID {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update user status"
        )