#backend/app/models/user.py

from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Set
from pydantic import BaseModel, EmailStr, Field, validator
import re

from .common import TimestampedModel, PyObjectId
from ..core.constants import UserRole, UserStatus

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

    def expire_session(self) -> None:
        """Mark session as expired."""
        self.is_active = False
        self.expires_at = datetime.utcnow()

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
    
    class Config:
        """Model configuration."""
        validate_assignment = True
        json_encoders = {
            datetime: lambda dt: dt.isoformat(),
            PyObjectId: str
        }

    def create_session(
        self,
        user_agent: str,
        ip_address: str,
        device_info: Dict[str, str]
    ) -> UserSession:
        """Create new user session."""
        # Clean expired sessions
        self.clean_expired_sessions()
        
        # Check max sessions
        if len([s for s in self.active_sessions if s.is_active]) >= self.max_sessions:
            # Expire oldest session
            oldest_session = sorted(
                [s for s in self.active_sessions if s.is_active],
                key=lambda x: x.last_activity
            )[0]
            oldest_session.expire_session()
        
        # Create new session
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
            }
        )

    def add_custom_permission(
        self,
        permission: UserPermission
    ) -> None:
        """Add custom permission to user."""
        self.role_assignment.custom_permissions.append(permission)

    def has_permission(
        self,
        permission_name: str,
        resource_id: Optional[str] = None
    ) -> bool:
        """Check if user has specific permission."""
        # Check role-based permissions
        if permission_name in self.role_assignment.permissions:
            return True
            
        # Check custom permissions
        for permission in self.role_assignment.custom_permissions:
            if (
                permission.name == permission_name and
                (not resource_id or permission.resource_id == resource_id) and
                (not permission.expires_at or permission.expires_at > datetime.utcnow())
            ):
                return True
                
        return False

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