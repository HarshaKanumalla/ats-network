"""Admin routes and endpoint handlers."""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
from typing import List
import logging
from datetime import datetime

from ..models.user import User, UserStatus, UserResponse
from ..services.auth import get_current_admin_user
from ..services.database import update_user_status, get_pending_users
from ..services.email import send_approval_email, send_rejection_email

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/pending-users", response_model=List[User])
async def list_pending_users(
    current_admin: User = Depends(get_current_admin_user)
) -> List[User]:
    """
    Retrieve all pending user registrations.

    This endpoint allows administrators to view all users with pending registration
    status. It requires admin privileges to access.

    Args:
        current_admin: The authenticated admin user making the request

    Returns:
        A list of User objects with pending status

    Raises:
        HTTPException: If there's an error fetching the users or if access is denied
    """
    try:
        users = await get_pending_users()
        logger.info(f"Retrieved {len(users)} pending users")
        return users
    except Exception as e:
        logger.error(f"Error fetching pending users: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve pending users"
        )

@router.post("/users/{user_id}/approve", response_model=UserResponse)
async def approve_user(
    user_id: str,
    background_tasks: BackgroundTasks,
    current_admin: User = Depends(get_current_admin_user)
) -> UserResponse:
    """
    Approve a pending user registration.

    This endpoint allows administrators to approve user registrations. Upon approval,
    the user's status is updated and a notification email is sent.

    Args:
        user_id: The ID of the user to approve
        background_tasks: FastAPI background tasks handler
        current_admin: The authenticated admin user making the request

    Returns:
        UserResponse object containing the updated user information

    Raises:
        HTTPException: If user is not found or if there's an error during approval
    """
    try:
        logger.info(f"Processing user approval request for user ID: {user_id}")
        
        updated_user = await update_user_status(
            user_id=user_id,
            status=UserStatus.APPROVED
        )

        if not updated_user:
            logger.error(f"User not found for approval: {user_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Schedule approval email in background
        background_tasks.add_task(send_approval_email, updated_user)
        
        logger.info(f"User approval successful: {user_id}")
        
        return UserResponse(
            status="success",
            message="User approved successfully",
            data=updated_user
        )

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error during user approval: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to approve user"
        )

@router.post("/users/{user_id}/reject", response_model=UserResponse)
async def reject_user(
    user_id: str,
    reason: str,
    background_tasks: BackgroundTasks,
    current_admin: User = Depends(get_current_admin_user)
) -> UserResponse:
    """
    Reject a pending user registration.

    This endpoint allows administrators to reject user registrations with a specific
    reason. The user is notified via email about the rejection.

    Args:
        user_id: The ID of the user to reject
        reason: The reason for rejection
        background_tasks: FastAPI background tasks handler
        current_admin: The authenticated admin user making the request

    Returns:
        UserResponse object containing the rejection status

    Raises:
        HTTPException: If user is not found or if there's an error during rejection
    """
    try:
        logger.info(f"Processing user rejection for user ID: {user_id}")
        
        updated_user = await update_user_status(
            user_id=user_id,
            status=UserStatus.REJECTED
        )

        if not updated_user:
            logger.error(f"User not found for rejection: {user_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Schedule rejection email in background
        background_tasks.add_task(
            send_rejection_email,
            updated_user,
            reason
        )

        logger.info(f"User rejection processed: {user_id}")
        
        return UserResponse(
            status="success",
            message="User rejected successfully",
            data=updated_user
        )

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error during user rejection: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reject user"
        )

@router.get("/users/stats")
async def get_user_statistics(
    current_admin: User = Depends(get_current_admin_user)
):
    """
    Retrieve user-related statistics.

    This endpoint provides administrators with statistical information about user
    registrations, approvals, and rejections.

    Args:
        current_admin: The authenticated admin user making the request

    Returns:
        Dictionary containing user statistics
    """
    try:
        # Implementation for user statistics
        return {
            "total_users": 0,
            "pending_users": 0,
            "approved_users": 0,
            "rejected_users": 0
        }
    except Exception as e:
        logger.error(f"Error retrieving user statistics: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve user statistics"
        )