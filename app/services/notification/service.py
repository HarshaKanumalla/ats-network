# backend/app/services/notification/service.py

"""
Service for managing system notifications, alerts, and real-time updates.
Handles push notifications, in-app alerts, and notification preferences.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
import logging
from bson import ObjectId
import json

from ...core.exceptions import NotificationError
from ...database import get_database
from ...config import get_settings
from ...services.websocket import websocket_manager

logger = logging.getLogger(__name__)
settings = get_settings()

class NotificationService:
    """Service for managing all types of system notifications."""
    
    def __init__(self):
        """Initialize notification service."""
        self.db = None
        self.notification_types = {
            "test_complete": {
                "priority": "high",
                "retention_days": 30
            },
            "approval_required": {
                "priority": "high",
                "retention_days": 14
            },
            "maintenance_due": {
                "priority": "medium",
                "retention_days": 7
            },
            "system_alert": {
                "priority": "high",
                "retention_days": 90
            }
        }
        logger.info("Notification service initialized")

    async def send_notification(
        self,
        user_id: str,
        title: str,
        message: str,
        notification_type: str,
        data: Optional[Dict[str, Any]] = None,
        priority: Optional[str] = None
    ) -> Dict[str, Any]:
        """Send notification to specific user."""
        try:
            db = await get_database()
            
            # Create notification document
            notification = {
                "userId": ObjectId(user_id),
                "title": title,
                "message": message,
                "type": notification_type,
                "priority": priority or self.notification_types[notification_type]["priority"],
                "data": data or {},
                "status": "unread",
                "createdAt": datetime.utcnow()
            }
            
            # Store notification
            result = await db.notifications.insert_one(notification)
            notification["_id"] = result.inserted_id
            
            # Send real-time notification if user is online
            await self._send_realtime_notification(user_id, notification)
            
            logger.info(f"Sent notification to user: {user_id}")
            return notification
            
        except Exception as e:
            logger.error(f"Notification sending error: {str(e)}")
            raise NotificationError("Failed to send notification")

    async def get_user_notifications(
        self,
        user_id: str,
        status: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get notifications for specific user."""
        try:
            db = await get_database()
            
            # Build query
            query = {"userId": ObjectId(user_id)}
            if status:
                query["status"] = status
            
            # Get notifications
            cursor = db.notifications.find(query)
            cursor.sort("createdAt", -1).limit(limit)
            
            return await cursor.to_list(None)
            
        except Exception as e:
            logger.error(f"Notification retrieval error: {str(e)}")
            raise NotificationError("Failed to get notifications")

    async def mark_as_read(
        self,
        notification_ids: List[str],
        user_id: str
    ) -> int:
        """Mark notifications as read."""
        try:
            db = await get_database()
            
            # Update notifications
            result = await db.notifications.update_many(
                {
                    "_id": {"$in": [ObjectId(id) for id in notification_ids]},
                    "userId": ObjectId(user_id)
                },
                {
                    "$set": {
                        "status": "read",
                        "readAt": datetime.utcnow()
                    }
                }
            )
            
            return result.modified_count
            
        except Exception as e:
            logger.error(f"Notification status update error: {str(e)}")
            raise NotificationError("Failed to update notification status")

    async def _send_realtime_notification(
        self,
        user_id: str,
        notification: Dict[str, Any]
    ) -> None:
        """Send real-time notification through WebSocket."""
        try:
            await websocket_manager.send_to_user(
                user_id,
                {
                    "type": "notification",
                    "data": notification
                }
            )
        except Exception as e:
            logger.error(f"Real-time notification error: {str(e)}")

    async def cleanup_old_notifications(self) -> int:
        """Clean up old notifications based on retention policy."""
        try:
            db = await get_database()
            deleted_count = 0
            
            for notification_type, config in self.notification_types.items():
                retention_date = datetime.utcnow() - timedelta(
                    days=config["retention_days"]
                )
                
                result = await db.notifications.delete_many({
                    "type": notification_type,
                    "createdAt": {"$lt": retention_date}
                })
                
                deleted_count += result.deleted_count
            
            logger.info(f"Cleaned up {deleted_count} old notifications")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Notification cleanup error: {str(e)}")
            raise NotificationError("Failed to cleanup notifications")

# Initialize notification service
notification_service = NotificationService()