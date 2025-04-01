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
            
            # Log admin action
            await self.log_admin_action(
                action_type="registration_approval",
                user_id=approved_by,
                details={
                    "approved_user": str(user_id),
                    "role": role,
                    "center_id": center_id
                }
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
            
            # Log admin action
            await self.log_admin_action(
                action_type="registration_rejection",
                user_id=rejected_by,
                details={
                    "rejected_user": str(user_id),
                    "reason": reason
                }
            )
            
            logger.info(f"Rejected registration for user: {user_id}")
            return result
            
        except Exception as e:
            logger.error(f"Registration rejection error: {str(e)}")
            raise AdminError("Failed to reject registration")

    async def update_user_role(
        self,
        user_id: str,
        new_role: str,
        updated_by: str,
        center_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update user role with proper tracking."""
        try:
            db = await get_database()
            
            update_data = {
                "role": new_role,
                "updated_by": ObjectId(updated_by),
                "updated_at": datetime.utcnow()
            }
            
            if center_id:
                update_data["center_id"] = ObjectId(center_id)
            
            result = await db.users.find_one_and_update(
                {"_id": ObjectId(user_id)},
                {"$set": update_data},
                return_document=True
            )
            
            if not result:
                raise AdminError("User not found")
            
            # Log admin action
            await self.log_admin_action(
                action_type="role_update",
                user_id=updated_by,
                details={
                    "target_user": str(user_id),
                    "new_role": new_role,
                    "center_id": center_id
                }
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Role update error: {str(e)}")
            raise AdminError("Failed to update user role")

    async def manage_center_status(
        self,
        center_id: str,
        new_status: str,
        reason: str,
        updated_by: str
    ) -> Dict[str, Any]:
        """Update testing center status."""
        try:
            db = await get_database()
            
            result = await db.centers.find_one_and_update(
                {"_id": ObjectId(center_id)},
                {
                    "$set": {
                        "status": new_status,
                        "status_updated_at": datetime.utcnow(),
                        "status_updated_by": ObjectId(updated_by),
                        "status_reason": reason
                    },
                    "$push": {
                        "status_history": {
                            "status": new_status,
                            "reason": reason,
                            "updated_by": ObjectId(updated_by),
                            "updated_at": datetime.utcnow()
                        }
                    }
                },
                return_document=True
            )
            
            if not result:
                raise AdminError("Center not found")
            
            # Log admin action
            await self.log_admin_action(
                action_type="center_status_update",
                user_id=updated_by,
                details={
                    "center_id": str(center_id),
                    "new_status": new_status,
                    "reason": reason
                }
            )
                
            return result
            
        except Exception as e:
            logger.error(f"Center status update error: {str(e)}")
            raise AdminError("Failed to update center status")

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

    async def get_system_health(self) -> Dict[str, Any]:
        """Get system health metrics."""
        try:
            db = await get_database()
            
            # Database stats
            db_stats = await db.command("dbStats")
            
            # Application metrics
            active_sessions = await db.sessions.count_documents({"status": "active"})
            error_count = await db.error_logs.count_documents({
                "timestamp": {
                    "$gte": datetime.utcnow().replace(hour=0, minute=0, second=0)
                }
            })
            
            # Storage metrics
            storage_usage = await s3_service.get_storage_usage()
            
            health_data = {
                "database": {
                    "size": db_stats["dataSize"],
                    "collections": db_stats["collections"],
                    "indexes": db_stats["indexes"]
                },
                "application": {
                    "active_sessions": active_sessions,
                    "error_count_today": error_count,
                    "uptime": await self.get_application_uptime()
                },
                "storage": storage_usage,
                "timestamp": datetime.utcnow()
            }
            
            # Log health check
            await self.log_admin_action(
                action_type="health_check",
                user_id="system",
                details=health_data
            )
            
            return health_data
            
        except Exception as e:
            logger.error(f"System health check error: {str(e)}")
            raise AdminError("Failed to fetch system health metrics")

    async def update_system_config(
        self,
        config_updates: Dict[str, Any],
        updated_by: str
    ) -> Dict[str, Any]:
        """Update system configuration."""
        try:
            db = await get_database()
            
            # Validate configuration updates
            valid_configs = ["session_timeout", "max_login_attempts", "maintenance_mode"]
            invalid_configs = [k for k in config_updates.keys() if k not in valid_configs]
            
            if invalid_configs:
                raise AdminError(f"Invalid configuration keys: {invalid_configs}")
            
            result = await db.system_config.find_one_and_update(
                {"_id": "global_config"},
                {
                    "$set": {
                        **config_updates,
                        "updated_by": ObjectId(updated_by),
                        "updated_at": datetime.utcnow()
                    },
                    "$push": {
                        "update_history": {
                            "changes": config_updates,
                            "updated_by": ObjectId(updated_by),
                            "updated_at": datetime.utcnow()
                        }
                    }
                },
                upsert=True,
                return_document=True
            )
            
            # Log configuration change
            await self.log_admin_action(
                action_type="config_update",
                user_id=updated_by,
                details={"updates": config_updates}
            )
            
            # Clear configuration cache if exists
            if hasattr(settings, 'clear_cache'):
                settings.clear_cache()
            
            return result
            
        except Exception as e:
            logger.error(f"Configuration update error: {str(e)}")
            raise AdminError("Failed to update system configuration")

    async def log_admin_action(
        self,
        action_type: str,
        user_id: str,
        details: Dict[str, Any]
    ) -> None:
        """Log administrative actions."""
        try:
            db = await get_database()
            
            await db.admin_logs.insert_one({
                "action_type": action_type,
                "user_id": ObjectId(user_id) if user_id != "system" else "system",
                "details": details,
                "timestamp": datetime.utcnow(),
                "ip_address": details.get("ip_address"),
                "user_agent": details.get("user_agent")
            })
            
        except Exception as e:
            logger.error(f"Admin action logging error: {str(e)}")

    async def get_application_uptime(self) -> int:
        """Get application uptime in seconds."""
        try:
            db = await get_database()
            startup_log = await db.system_logs.find_one(
                {"event_type": "startup"},
                sort=[("timestamp", -1)]
            )
            if startup_log:
                return int((datetime.utcnow() - startup_log["timestamp"]).total_seconds())
            return 0
        except Exception as e:
            logger.error(f"Error fetching application uptime: {str(e)}")
            return 0

# Initialize admin service
admin_service = AdminService()