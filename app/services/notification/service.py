from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import logging
import asyncio
from bson import ObjectId
import jinja2

from ...core.exceptions import NotificationError
from ...services.websocket import websocket_manager
from ...services.email import email_service
from ...database import get_database, database_transaction
from ...config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class NotificationService:
    """Enhanced service for managing system-wide notifications."""
    
    def __init__(self):
        """Initialize notification service with enhanced features."""
        self.db = None
        
        # Initialize template engine
        self.template_loader = jinja2.FileSystemLoader('app/templates/notifications')
        self.template_env = jinja2.Environment(
            loader=self.template_loader,
            autoescape=True
        )
        
        # Notification categories and priorities
        self.notification_types = {
            "test_complete": {
                "priority": "high",
                "channels": ["email", "in_app", "websocket"],
                "template": "test_complete.html",
                "retention_days": 30
            },
            "approval_required": {
                "priority": "high",
                "channels": ["email", "in_app"],
                "template": "approval_required.html",
                "retention_days": 14
            },
            "maintenance_due": {
                "priority": "medium",
                "channels": ["email", "in_app"],
                "template": "maintenance_due.html",
                "retention_days": 7
            },
            "system_alert": {
                "priority": "high",
                "channels": ["email", "in_app", "websocket"],
                "template": "system_alert.html",
                "retention_days": 90
            }
        }
        
        # Delivery settings
        self.retry_settings = {
            "max_attempts": 3,
            "retry_delay": 300,  # 5 minutes
            "exponential_backoff": True
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
        """Send notification with multi-channel delivery."""
        try:
            db = await get_database()
            
            # Validate notification type
            type_config = self.notification_types.get(notification_type)
            if not type_config:
                raise NotificationError("Invalid notification type")
            
            # Create notification document
            notification = {
                "userId": ObjectId(user_id),
                "title": title,
                "message": message,
                "type": notification_type,
                "priority": priority or type_config["priority"],
                "data": data or {},
                "status": "pending",
                "channels": [],
                "createdAt": datetime.utcnow()
            }
            
            # Store notification
            async with database_transaction() as session:
                result = await db.notifications.insert_one(
                    notification,
                    session=session
                )
                notification["_id"] = result.inserted_id
                
                # Process delivery channels
                delivery_tasks = []
                for channel in type_config["channels"]:
                    delivery_tasks.append(
                        self._deliver_notification(
                            str(result.inserted_id),
                            channel,
                            notification
                        )
                    )
                
                # Wait for deliveries to complete
                await asyncio.gather(*delivery_tasks)
            
            logger.info(f"Sent notification to user: {user_id}")
            return notification
            
        except Exception as e:
            logger.error(f"Notification sending error: {str(e)}")
            raise NotificationError("Failed to send notification")

    async def send_bulk_notification(
        self,
        user_ids: List[str],
        title: str,
        message: str,
        notification_type: str,
        data: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Send notification to multiple users efficiently."""
        try:
            db = await get_database()
            notifications = []
            
            # Process in batches
            batch_size = 100
            for i in range(0, len(user_ids), batch_size):
                batch = user_ids[i:i + batch_size]
                
                # Create notification documents
                notification_docs = [
                    {
                        "userId": ObjectId(user_id),
                        "title": title,
                        "message": message,
                        "type": notification_type,
                        "data": data or {},
                        "status": "pending",
                        "createdAt": datetime.utcnow()
                    }
                    for user_id in batch
                ]
                
                # Insert batch
                result = await db.notifications.insert_many(notification_docs)
                
                # Process deliveries
                delivery_tasks = []
                for notification in notification_docs:
                    for channel in self.notification_types[notification_type]["channels"]:
                        delivery_tasks.append(
                            self._deliver_notification(
                                str(notification["_id"]),
                                channel,
                                notification
                            )
                        )
                
                await asyncio.gather(*delivery_tasks)
                notifications.extend(notification_docs)
            
            return notifications
            
        except Exception as e:
            logger.error(f"Bulk notification error: {str(e)}")
            raise NotificationError("Failed to send bulk notifications")

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

    async def _deliver_notification(
        self,
        notification_id: str,
        channel: str,
        notification: Dict[str, Any]
    ) -> None:
        """Handle notification delivery through specific channel."""
        try:
            if channel == "email":
                await self._send_email_notification(notification)
            elif channel == "websocket":
                await self._send_websocket_notification(notification)
            elif channel == "in_app":
                await self._store_in_app_notification(notification)
            
            # Update delivery status
            await self._update_delivery_status(
                notification_id,
                channel,
                "delivered"
            )
            
        except Exception as e:
            logger.error(f"Delivery error for channel {channel}: {str(e)}")
            
            # Handle retry if needed
            if await self._should_retry_delivery(notification_id, channel):
                await self._schedule_retry(
                    notification_id,
                    channel,
                    notification
                )

    async def _send_email_notification(
        self,
        notification: Dict[str, Any]
    ) -> None:
        """Send notification via email."""
        try:
            # Get user email
            db = await get_database()
            user = await db.users.find_one(
                {"_id": notification["userId"]}
            )
            if not user:
                raise NotificationError("User not found")
            
            # Generate email content
            template = self.template_env.get_template(
                self.notification_types[notification["type"]]["template"]
            )
            html_content = template.render(**notification)
            
            # Send email
            await email_service.send_email(
                recipient=user["email"],
                subject=notification["title"],
                html_content=html_content
            )
            
        except Exception as e:
            logger.error(f"Email notification error: {str(e)}")
            raise NotificationError("Failed to send email notification")

    async def _send_websocket_notification(
        self,
        notification: Dict[str, Any]
    ) -> None:
        """Send notification via WebSocket."""
        try:
            await websocket_manager.send_to_user(
                str(notification["userId"]),
                {
                    "type": "notification",
                    "data": notification
                }
            )
            
        except Exception as e:
            logger.error(f"WebSocket notification error: {str(e)}")
            raise NotificationError("Failed to send WebSocket notification")

    async def _store_in_app_notification(
        self,
        notification: Dict[str, Any]
    ) -> None:
        """Store notification for in-app display."""
        try:
            db = await get_database()
            
            await db.in_app_notifications.insert_one({
                "userId": notification["userId"],
                "notification": notification,
                "createdAt": datetime.utcnow(),
                "expiresAt": datetime.utcnow() + timedelta(
                    days=self.notification_types[notification["type"]]["retention_days"]
                )
            })
            
        except Exception as e:
            logger.error(f"In-app notification storage error: {str(e)}")
            raise NotificationError("Failed to store in-app notification")

    async def _update_delivery_status(
        self,
        notification_id: str,
        channel: str,
        status: str
    ) -> None:
        """Update notification delivery status."""
        try:
            db = await get_database()
            
            await db.notifications.update_one(
                {"_id": ObjectId(notification_id)},
                {
                    "$push": {
                        "channels": {
                            "name": channel,
                            "status": status,
                            "updatedAt": datetime.utcnow()
                        }
                    }
                }
            )
            
        except Exception as e:
            logger.error(f"Status update error: {str(e)}")

    async def _should_retry_delivery(
        self,
        notification_id: str,
        channel: str
    ) -> bool:
        """Determine if a delivery should be retried."""
        try:
            db = await get_database()
            notification = await db.notifications.find_one({"_id": ObjectId(notification_id)})
            if not notification:
                return False

            retries = sum(1 for c in notification.get("channels", []) if c["name"] == channel and c["status"] == "failed")
            return retries < self.retry_settings["max_attempts"]
        except Exception as e:
            logger.error(f"Retry check error: {str(e)}")
            return False

    async def _schedule_retry(
        self,
        notification_id: str,
        channel: str,
        notification: Dict[str, Any]
    ) -> None:
        """Schedule a retry for a failed delivery."""
        try:
            delay = self.retry_settings["retry_delay"]
            if self.retry_settings["exponential_backoff"]:
                retries = sum(1 for c in notification.get("channels", []) if c["name"] == channel and c["status"] == "failed")
                delay *= (2 ** retries)

            logger.info(f"Scheduling retry for notification {notification_id} on channel {channel} in {delay} seconds")
            await asyncio.sleep(delay)
            await self._deliver_notification(notification_id, channel, notification)
        except Exception as e:
            logger.error(f"Retry scheduling error: {str(e)}")

    async def _cleanup_expired_notifications(self) -> None:
        """Clean up expired in-app notifications."""
        try:
            db = await get_database()
            await db.in_app_notifications.delete_many({
                "expiresAt": {"$lt": datetime.utcnow()}
            })
            logger.info("Expired notifications cleaned up")
        except Exception as e:
            logger.error(f"Notification cleanup error: {str(e)}")

# Initialize notification service
notification_service = NotificationService()