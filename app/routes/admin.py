# backend/app/routes/admin.py
from fastapi import APIRouter, HTTPException, status, Depends, BackgroundTasks
from typing import List
import logging
from datetime import datetime

from ..models.user import User, UserStatus
from ..services.auth import get_current_admin_user
from ..services.database import update_user_status, get_pending_users
from ..services.email import send_approval_email, send_rejection_email

# Set up logging
logger = logging.getLogger(__name__)

# System Info
SYSTEM_INFO = {
    "last_updated": "2024-12-19 18:04:16",
    "updated_by": "HarshaKanumalla"
}

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(get_current_admin_user)]
)

@router.get("/pending-users", response_model=List[User])
async def list_pending_users(current_admin: User = Depends(get_current_admin_user)):
    """Get all pending user registrations."""
    try:
        users = await get_pending_users()
        return users
    except Exception as e:
        logger.error(f"Error fetching pending users: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch pending users"
        )

@router.post("/approve-user/{user_id}")
async def approve_user(
    user_id: str,
    background_tasks: BackgroundTasks,
    current_admin: User = Depends(get_current_admin_user)
):
    """Approve a pending user registration."""
    try:
        # Update user status
        updated_user = await update_user_status(
            user_id=user_id,
            status=UserStatus.APPROVED,
            updated_at=datetime.utcnow()
        )

        if not updated_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Send approval email in background
        background_tasks.add_task(send_approval_email, updated_user)

        return {"message": "User approved successfully"}
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error approving user: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to approve user"
        )

@router.post("/reject-user/{user_id}")
async def reject_user(
    user_id: str,
    reason: str,
    background_tasks: BackgroundTasks,
    current_admin: User = Depends(get_current_admin_user)
):
    """Reject a pending user registration."""
    try:
        # Update user status
        updated_user = await update_user_status(
            user_id=user_id,
            status=UserStatus.REJECTED,
            updated_at=datetime.utcnow()
        )

        if not updated_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Send rejection email in background
        background_tasks.add_task(send_rejection_email, updated_user, reason)

        return {"message": "User rejected successfully"}
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error rejecting user: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reject user"
        )