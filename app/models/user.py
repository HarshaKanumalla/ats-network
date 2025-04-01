from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Set
from pydantic import BaseModel, EmailStr, Field, validator, field_validator
from zoneinfo import ZoneInfo
import re
import secrets
import logging

from .common import TimestampedModel, PyObjectId
from ..core.constants import UserRole, UserStatus

logger = logging.getLogger(__name__)

class UserSession(BaseModel):
    """User session tracking model."""
    
    session_id: str = Field(..., min_length=32, max_length=64)
    user_agent: str
    ip_address: str
    login_time: datetime
    last_activity: datetime
    is_active: bool = True
    expires_at: datetime
    device_info: Dict[str, str]
    
    def update_activity(self) -> None:
        """Update session last activity time."""
        self.last_activity = datetime.utcnow()
        logger.debug(f"Session {self.session_id} activity updated")

    def expire_session(self) -> None:
        """Mark session as expired."""
        self.is_active = False
        self.expires_at = datetime.utcnow()
        logger.info(f"Session {self.session_id} expired")

class UserPermission(BaseModel):
    """User permission definition."""
    
    name: str
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    granted_at: datetime
    granted_by: PyObjectId
    expires_at: Optional[datetime] = None
    constraints: Dict[str, Any] = Field(default_factory=dict)

class ActivityLog(BaseModel):
    """User activity tracking model."""
    
    VALID_ACTIVITY_TYPES = [
        "login", "logout", "password_change", "role_update", 
        "permission_change", "profile_update", "security_action"
    ]
    VALID_STATUSES = ["success", "failure", "pending", "cancelled"]
    
    activity_type: str
    timestamp: datetime
    ip_address: str
    user_agent: str
    session_id: Optional[str]
    resource_type: Optional[str]
    resource_id: Optional[str]
    details: Dict[str, Any]
    status: str
    location_info: Optional[Dict[str, Any]]

    @field_validator('activity_type')
    def validate_activity_type(cls, v: str) -> str:
        if v not in cls.VALID_ACTIVITY_TYPES:
            raise ValueError(f"Invalid activity type. Must be one of: {cls.VALID_ACTIVITY_TYPES}")
        return v

    @field_validator('status')
    def validate_status(cls, v: str) -> str:
        if v not in cls.VALID_STATUSES:
            raise ValueError(f"Invalid status. Must be one of: {cls.VALID_STATUSES}")
        return v

class SecurityProfile(BaseModel):
    """User security profile."""
    
    password_hash: str
    password_updated_at: datetime
    password_history: List[Dict[str, Any]] = []
    failed_login_attempts: int = 0
    last_failed_login: Optional[datetime] = None
    locked_until: Optional[datetime] = None
    security_questions: List[Dict[str, str]] = []
    two_factor_enabled: bool = False
    two_factor_method: Optional[str] = None

    def record_failed_login(self) -> None:
        """Record failed login attempt."""
        self.failed_login_attempts += 1
        self.last_failed_login = datetime.utcnow()
        
        if self.failed_login_attempts >= 5:
            self.locked_until = datetime.utcnow() + timedelta(minutes=30)
            logger.warning(f"Account locked due to multiple failed attempts")

    def reset_failed_attempts(self) -> None:
        """Reset failed login attempts counter."""
        self.failed_login_attempts = 0
        self.last_failed_login = None
        self.locked_until = None
        logger.info("Failed login attempts reset")

    def add_password_to_history(self, password_hash: str) -> None:
        """Add password to history."""
        self.password_history.append({
            "hash": password_hash,
            "created_at": datetime.utcnow()
        })
        if len(self.password_history) > 5:  # Keep last 5 passwords
            self.password_history.pop(0)
        logger.debug("Password added to history")

class RoleAssignment(BaseModel):
    """User role assignment details."""
    
    role: UserRole
    assigned_at: datetime
    assigned_by: PyObjectId
    expires_at: Optional[datetime] = None
    center_id: Optional[PyObjectId] = None
    permissions: Set[str] = set()
    custom_permissions: List[UserPermission] = []

class UserProfile(BaseModel):
    """User profile information."""
    
    full_name: str
    phone_number: str
    profile_photo_url: Optional[str] = None
    designation: Optional[str] = None
    department: Optional[str] = None
    bio: Optional[str] = None
    preferred_language: str = "en"
    notification_preferences: Dict[str, bool] = Field(default_factory=dict)

class UserCreate(BaseModel):
    """User creation model."""
    
    email: EmailStr
    password: str = Field(..., min_length=8)
    confirm_password: str
    full_name: str
    phone_number: str
    ats_name: Optional[str] = None
    ats_address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pin_code: Optional[str] = None
    
    @validator('password')
    def validate_password_strength(cls, v: str) -> str:
        """Validate password strength."""
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        if not re.search(r'[A-Z]', v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r'[a-z]', v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r'\d', v):
            raise ValueError("Password must contain at least one digit")
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', v):
            raise ValueError("Password must contain at least one special character")
        return v

    @validator('confirm_password')
    def passwords_match(cls, v: str, values: Dict[str, Any]) -> str:
        """Validate password confirmation."""
        if 'password' in values and v != values['password']:
            raise ValueError('Passwords do not match')
        return v
    
    @validator('phone_number')
    def validate_phone(cls, v: str) -> str:
        """Validate phone number format."""
        pattern = r'^\+?[1-9]\d{9,14}$'
        if not re.match(pattern, v):
            raise ValueError('Invalid phone number format')
        return v

class User(TimestampedModel):
    """Enhanced user model with comprehensive tracking."""
    
    email: EmailStr = Field(..., unique=True)
    profile: UserProfile
    role_assignment: RoleAssignment
    security: SecurityProfile
    status: UserStatus = UserStatus.PENDING
    
    # Center association
    center_id: Optional[PyObjectId] = None
    center_role: Optional[str] = None
    
    # Session management
    active_sessions: List[UserSession] = []
    max_sessions: int = 5
    
    # Activity tracking
    activity_logs: List[ActivityLog] = []
    last_login: Optional[datetime] = None
    last_active: Optional[datetime] = None
    
    # Account verification
    is_verified: bool = False
    verification_token: Optional[str] = None
    verification_sent_at: Optional[datetime] = None
    
    # Password reset
    reset_token: Optional[str] = None
    reset_token_expires: Optional[datetime] = None

    def get_active_session(self, session_id: str) -> Optional[UserSession]:
        """Get active session by ID."""
        return next(
            (s for s in self.active_sessions 
             if s.session_id == session_id and s.is_active),
            None
        )

    def invalidate_all_sessions(self) -> None:
        """Invalidate all active sessions."""
        current_time = datetime.utcnow()
        for session in self.active_sessions:
            if session.is_active:
                session.expire_session()
        self.log_activity(
            activity_type="security_action",
            session_id=None,
            details={"action": "invalidate_all_sessions"},
            ip_address="system",
            user_agent="system",
            status="success"
        )
        logger.info(f"All sessions invalidated for user {self.email}")

    def update_profile(
        self,
        updates: Dict[str, Any],
        session_id: Optional[str] = None
    ) -> None:
        """Update user profile with tracking."""
        old_values = {
            k: getattr(self.profile, k)
            for k in updates.keys()
            if hasattr(self.profile, k)
        }
        
        for key, value in updates.items():
            if hasattr(self.profile, key):
                setattr(self.profile, key, value)
        
        self.log_activity(
            activity_type="profile_update",
            session_id=session_id,
            details={
                "updated_fields": list(updates.keys()),
                "old_values": old_values,
                "new_values": updates
            },
            ip_address="system",
            user_agent="system",
            status="success"
        )
        logger.info(f"Profile updated for user {self.email}")

    def create_session(
        self,
        user_agent: str,
        ip_address: str,
        device_info: Dict[str, str]
    ) -> UserSession:
        """Create new user session."""
        self.clean_expired_sessions()
        
        if len([s for s in self.active_sessions if s.is_active]) >= self.max_sessions:
            oldest_session = sorted(
                [s for s in self.active_sessions if s.is_active],
                key=lambda x: x.last_activity
            )[0]
            oldest_session.expire_session()
        
        session = UserSession(
            session_id=secrets.token_urlsafe(32),
            user_agent=user_agent,
            ip_address=ip_address,
            login_time=datetime.utcnow(),
            last_activity=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(days=1),
            device_info=device_info
        )
        
        self.active_sessions.append(session)
        return session

    def log_activity(
        self,
        activity_type: str,
        session_id: Optional[str],
        details: Dict[str, Any],
        **kwargs
    ) -> None:
        """Log user activity."""
        log_entry = ActivityLog(
            activity_type=activity_type,
            timestamp=datetime.utcnow(),
            session_id=session_id,
            details=details,
            **kwargs
        )
        self.activity_logs.append(log_entry)
        self.last_active = datetime.utcnow()

    def update_role(
        self,
        new_role: UserRole,
        updated_by: PyObjectId,
        center_id: Optional[PyObjectId] = None
    ) -> None:
        """Update user role with proper tracking."""
        old_role = self.role_assignment.role
        self.role_assignment = RoleAssignment(
            role=new_role,
            assigned_at=datetime.utcnow(),
            assigned_by=updated_by,
            center_id=center_id
        )
        
        self.log_activity(
            activity_type="role_update",
            session_id=None,
            details={
                "old_role": old_role,
                "new_role": new_role,
                "updated_by": str(updated_by)
            },
            ip_address="system",
            user_agent="system",
            status="success"
        )

    def clean_expired_sessions(self) -> None:
        """Clean up expired sessions."""
        current_time = datetime.utcnow()
        for session in self.active_sessions:
            if session.is_active and current_time >= session.expires_at:
                session.expire_session()

    def get_activity_summary(
        self,
        days: int = 30
    ) -> Dict[str, Any]:
        """Get user activity summary for specified period."""
        start_date = datetime.utcnow() - timedelta(days=days)
        recent_activities = [
            log for log in self.activity_logs
            if log.timestamp >= start_date
        ]
        
        return {
            "total_activities": len(recent_activities),
            "activity_types": {
                activity_type: len([
                    log for log in recent_activities
                    if log.activity_type == activity_type
                ])
                for activity_type in set(log.activity_type for log in recent_activities)
            },
            "last_active": self.last_active,
            "active_sessions": len([s for s in self.active_sessions if s.is_active])
        }

    class Config:
        """Model configuration."""
        validate_assignment = True
        json_encoders = {
            datetime: lambda dt: dt.isoformat(),
            PyObjectId: str
        }