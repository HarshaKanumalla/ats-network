from datetime import datetime
from typing import Optional, List, Dict, Any, Set
from pydantic import BaseModel, Field, validator, field_validator
from enum import Enum
import re
import logging

from .common import TimestampedModel, PyObjectId
from ..core.constants import NotificationType

logger = logging.getLogger(__name__)

class DeliveryMethod(str, Enum):
    """Notification delivery method options."""
    EMAIL = "email"
    IN_APP = "in_app"
    SMS = "sms"
    PUSH = "push"
    WEBHOOK = "webhook"

    @classmethod
    def _missing_(cls, value: str) -> Optional['DeliveryMethod']:
        """Handle case-insensitive lookup."""
        try:
            return cls[value.upper()]
        except KeyError:
            for member in cls:
                if member.value.lower() == value.lower():
                    return member
            return None

class Priority(str, Enum):
    """Notification priority levels."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"

class NotificationTemplate(TimestampedModel):
    """Notification template configuration."""
    
    template_code: str = Field(..., regex=r'^TPL\d{6}$')
    template_type: NotificationType
    subject_template: str
    content_template: str
    
    supported_delivery_methods: List[DeliveryMethod]
    default_priority: Priority = Priority.NORMAL
    
    parameters: List[str] = []
    required_permissions: List[str] = []
    metadata_fields: List[str] = []
    
    is_active: bool = True
    version: str = "1.0.0"
    last_modified_by: PyObjectId

    @field_validator('template_code')
    def validate_template_code(cls, v: str) -> str:
        """Validate template code format."""
        if not v.startswith('TPL'):
            raise ValueError("Template code must start with 'TPL'")
        return v

    @field_validator('content_template')
    def validate_content_template(cls, v: str) -> str:
        """Validate template content."""
        required_placeholders = set(re.findall(r'\{(\w+)\}', v))
        if not all(p in cls.parameters for p in required_placeholders):
            raise ValueError("Template contains undefined parameters")
        return v

class DeliveryAttempt(BaseModel):
    """Notification delivery attempt tracking."""
    
    method: DeliveryMethod
    attempt_time: datetime
    status: str
    error_details: Optional[Dict[str, Any]] = None
    delivery_metadata: Dict[str, Any] = Field(default_factory=dict)
    retry_count: int = 0

class NotificationPreferences(BaseModel):
    """User notification preferences."""
    
    user_id: PyObjectId
    enabled_types: Set[NotificationType] = set()
    enabled_methods: Set[DeliveryMethod] = set()
    quiet_hours: Optional[Dict[str, str]] = None
    frequency_limit: Optional[Dict[str, int]] = None
    priority_threshold: Priority = Priority.LOW

    def can_send_notification(self, notification_type: NotificationType, 
                            method: DeliveryMethod, 
                            current_time: datetime) -> bool:
        """Check if notification can be sent based on preferences."""
        try:
            # Check if type and method are enabled
            if (notification_type not in self.enabled_types or 
                method not in self.enabled_methods):
                return False

            # Check quiet hours
            if self.quiet_hours:
                current_hour = current_time.hour
                start_hour = int(self.quiet_hours.get('start', '22'))
                end_hour = int(self.quiet_hours.get('end', '7'))
                if start_hour <= current_hour or current_hour < end_hour:
                    logger.debug(f"Notification blocked during quiet hours for user {self.user_id}")
                    return False

            # Check frequency limits
            if self.frequency_limit:
                # Implementation for frequency checking would go here
                pass

            return True
        except Exception as e:
            logger.error(f"Error checking notification preferences: {str(e)}")
            return False

class NotificationQueue(TimestampedModel):
    """Queue management for notifications."""
    
    queue_id: str = Field(..., min_length=10)
    priority_level: Priority
    notifications: List[str] = Field(default_factory=list)
    status: str = "active"
    processing_window: Optional[Dict[str, datetime]] = None
    retry_policy: Dict[str, Any] = Field(
        default_factory=lambda: {
            "max_retries": 3,
            "retry_delay": 300,  # seconds
            "backoff_factor": 2
        }
    )

    def add_to_queue(self, notification_id: str) -> None:
        """Add notification to queue."""
        if notification_id not in self.notifications:
            self.notifications.append(notification_id)
            logger.info(f"Added notification {notification_id} to queue {self.queue_id}")

    def get_next_batch(self, batch_size: int = 10) -> List[str]:
        """Get next batch of notifications to process."""
        return self.notifications[:batch_size]

class NotificationGroup(BaseModel):
    """Group of related notifications."""
    
    group_id: str
    group_type: str
    notifications: List[str]  # List of notification IDs
    summary: str
    created_at: datetime
    expires_at: Optional[datetime] = None
    is_active: bool = True

class Notification(TimestampedModel):
    """Complete notification management model."""
    
    notification_id: str = Field(..., min_length=12)
    template_id: Optional[PyObjectId] = None
    sender_id: PyObjectId
    recipient_id: PyObjectId
    
    notification_type: NotificationType
    priority: Priority
    subject: str
    content: str
    
    delivery_methods: List[DeliveryMethod]
    delivery_attempts: List[DeliveryAttempt] = []
    delivery_status: Dict[str, str] = Field(default_factory=dict)
    
    group_id: Optional[str] = None
    related_resource: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    read_status: bool = False
    read_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    
    action_required: bool = False
    action_taken: Optional[Dict[str, Any]] = None

    def handle_delivery_error(self, method: DeliveryMethod, 
                            error: Exception) -> None:
        """Handle delivery errors with proper logging."""
        try:
            error_details = {
                "error_type": error.__class__.__name__,
                "error_message": str(error),
                "timestamp": datetime.utcnow()
            }
            
            self.add_delivery_attempt(method, "failed", error_details)
            
            if not self.can_retry_delivery(method):
                self.delivery_status[method] = "permanently_failed"
                logger.error(f"Permanent delivery failure for notification {self.notification_id}")
            else:
                logger.warning(f"Temporary delivery failure for notification {self.notification_id}")
        except Exception as e:
            logger.error(f"Error handling delivery failure: {str(e)}")

    class Config:
        """Model configuration."""
        validate_assignment = True
        json_encoders = {
            datetime: lambda dt: dt.isoformat(),
            PyObjectId: str
        }

class NotificationBatch(TimestampedModel):
    """Batch notification processing model."""
    
    batch_id: str
    template_id: PyObjectId
    sender_id: PyObjectId
    
    recipients: List[PyObjectId]
    delivery_methods: List[DeliveryMethod]
    priority: Priority
    
    parameters: Dict[str, Any]
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    processing_status: str = "pending"
    processed_count: int = 0
    failed_count: int = 0
    
    notifications: List[str] = []  # List of generated notification IDs
    error_details: Optional[Dict[str, Any]] = None

    def process_batch(self) -> None:
        """Process all notifications in batch."""
        try:
            logger.info(f"Starting batch processing for {self.batch_id}")
            self.processing_status = "processing"
            total_recipients = len(self.recipients)
            
            for recipient_id in self.recipients:
                try:
                    notification = self._create_notification(recipient_id)
                    self.add_notification(notification.notification_id, True)
                    logger.debug(f"Processed notification for recipient {recipient_id}")
                except Exception as e:
                    self.add_notification(str(recipient_id), False)
                    if not self.error_details:
                        self.error_details = {}
                    self.error_details[str(recipient_id)] = str(e)
                    logger.error(f"Failed to process notification for recipient {recipient_id}: {str(e)}")

            final_status = "completed" if self.failed_count == 0 else "completed_with_errors"
            self.processing_status = final_status
            logger.info(f"Batch processing completed. Status: {final_status}")
            
        except Exception as e:
            self.update_processing_status("failed", {"error": str(e)})
            logger.error(f"Batch processing failed: {str(e)}")
            raise

    def _create_notification(self, recipient_id: PyObjectId) -> 'Notification':
        """Create individual notification from batch template."""
        # Implementation for creating individual notifications
        pass