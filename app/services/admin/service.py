# backend/app/services/admin/service.py

"""
Administrative service handling user management, approvals, and system monitoring.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
import logging
from bson import ObjectId

from ...core.exceptions import AdminError
from ...models.user import User, UserCreate, UserUpdate
from ...services.email import email_service
from ...services.s3 import s3_service
from ...database import get_database
from ...config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class AdminService:
    """Service for handling administrative operations."""
    
    def __init__(self):
        """Initialize admin service."""
        self.db = None
        logger.info("Admin service initialized")

    async def get_pending_registrations(self) -> List[Dict[str, Any]]:
        """Get all pending user registrations."""
        try:
            db = await get_database()
            cursor = db.users.find({"status": "pending"})
            return await cursor.to_list(None)
        except Exception as e:
            logger.error(f"Error fetching pending registrations: {str(e)}")
            raise AdminError("Failed to fetch pending registrations")

    async def approve_registration(
        self,
        user_id: str,
        role: str,
        approved_by: str,
        center_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Approve user registration."""
        try:
            db = await get_database()
            
            # Update user status
            result = await db.users.find_one_and_update(
                {"_id": ObjectId(user_id)},
                {
                    "$set": {
                        "status": "active",
                        "role": role,
                        "center_id": ObjectId(center_id) if center_id else None,
                        "approved_by": ObjectId(approved_by),
                        "approved_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow()
                    }
                },
                return_document=True
            )
            
            if not result:
                raise AdminError("User not found")
            
            # Send approval notification
            await email_service.send_registration_approved(
                email=result["email"],
                name=result["full_name"],
                role=role
            )
            
            logger.info(f"Approved registration for user: {user_id}")
            return result
            
        except Exception as e:
            logger.error(f"Registration approval error: {str(e)}")
            raise AdminError("Failed to approve registration")

    async def reject_registration(
        self,
        user_id: str,
        reason: str,
        rejected_by: str
    ) -> Dict[str, Any]:
        """Reject user registration."""
        try:
            db = await get_database()
            
            # Update user status
            result = await db.users.find_one_and_update(
                {"_id": ObjectId(user_id)},
                {
                    "$set": {
                        "status": "rejected",
                        "rejection_reason": reason,
                        "rejected_by": ObjectId(rejected_by),
                        "rejected_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow()
                    }
                },
                return_document=True
            )
            
            if not result:
                raise AdminError("User not found")
            
            # Send rejection notification
            await email_service.send_registration_rejected(
                email=result["email"],
                name=result["full_name"],
                reason=reason
            )
            
            logger.info(f"Rejected registration for user: {user_id}")
            return result
            
        except Exception as e:
            logger.error(f"Registration rejection error: {str(e)}")
            raise AdminError("Failed to reject registration")

    async def get_system_statistics(self) -> Dict[str, Any]:
        """Get system-wide statistics."""
        try:
            db = await get_database()
            
            stats = {
                "users": {
                    "total": await db.users.count_documents({}),
                    "pending": await db.users.count_documents({"status": "pending"}),
                    "active": await db.users.count_documents({"status": "active"})
                },
                "centers": {
                    "total": await db.centers.count_documents({}),
                    "active": await db.centers.count_documents({"status": "active"})
                },
                "tests": {
                    "total": await db.testSessions.count_documents({}),
                    "completed": await db.testSessions.count_documents({"status": "completed"}),
                    "failed": await db.testSessions.count_documents({"status": "failed"})
                }
            }
            
            logger.info("Retrieved system statistics")
            return stats
            
        except Exception as e:
            logger.error(f"Error fetching system statistics: {str(e)}")
            raise AdminError("Failed to fetch system statistics")

# Initialize admin service
admin_service = AdminService()