#backend/app/models/notification.py

from datetime import datetime
from typing import Optional, List, Dict, Any, Set
from pydantic import BaseModel, Field, validator
from enum import Enum

from .common import TimestampedModel, PyObjectId
from ..core.constants import NotificationType

class DeliveryMethod(str, Enum):
    """Notification delivery method options."""
    EMAIL = "email"
    IN_APP = "in_app"
    SMS = "sms"
    PUSH = "push"
    WEBHOOK = "webhook"

class Priority(str, Enum):
    """Notification priority levels."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"

class NotificationTemplate(TimestampedModel):
    """Notification template configuration."""
    
    template_code: str
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
    
    class Config:
        """Model configuration."""
        validate_assignment = True
        json_encoders = {
            datetime: lambda dt: dt.isoformat(),
            PyObjectId: str
        }

    @validator('notification_id')
    def validate_notification_id(cls, v: str) -> str:
        """Validate notification ID format."""
        if not v.startswith('NOT'):
            raise ValueError("Notification ID must start with 'NOT'")
        return v

    def add_delivery_attempt(
        self,
        method: DeliveryMethod,
        status: str,
        error: Optional[Dict[str, Any]] = None
    ) -> None:
        """Add delivery attempt with tracking."""
        attempt = DeliveryAttempt(
            method=method,
            attempt_time=datetime.utcnow(),
            status=status,
            error_details=error,
            retry_count=len([
                a for a in self.delivery_attempts
                if a.method == method
            ])
        )
        self.delivery_attempts.append(attempt)
        self.delivery_status[method] = status

    def mark_as_read(self) -> None:
        """Mark notification as read."""
        self.read_status = True
        self.read_at = datetime.utcnow()

    def record_action(
        self,
        action_type: str,
        action_details: Dict[str, Any]
    ) -> None:
        """Record action taken on notification."""
        self.action_taken = {
            "type": action_type,
            "details": action_details,
            "timestamp": datetime.utcnow()
        }

    def is_expired(self) -> bool:
        """Check if notification has expired."""
        if not self.expires_at:
            return False
        return datetime.utcnow() > self.expires_at

    def can_retry_delivery(
        self,
        method: DeliveryMethod,
        max_retries: int = 3
    ) -> bool:
        """Check if delivery retry is possible."""
        attempts = [
            a for a in self.delivery_attempts
            if a.method == method
        ]
        return len(attempts) < max_retries

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

    def update_processing_status(
        self,
        new_status: str,
        error: Optional[Dict[str, Any]] = None
    ) -> None:
        """Update batch processing status."""
        self.processing_status = new_status
        if error:
            self.error_details = error

    def add_notification(
        self,
        notification_id: str,
        success: bool = True
    ) -> None:
        """Add processed notification to batch."""
        self.notifications.append(notification_id)
        if success:
            self.processed_count += 1
        else:
            self.failed_count += 1

    def get_completion_percentage(self) -> float:
        """Calculate batch processing completion percentage."""
        total = len(self.recipients)
        if total == 0:
            return 0.0
        return ((self.processed_count + self.failed_count) / total) * 100