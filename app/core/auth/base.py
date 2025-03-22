# backend/app/core/auth/base.py

from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import logging
from ...config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class AuthenticationBase:
    """Base class for authentication functionality."""
    
    def __init__(self):
        self.max_login_attempts = 5
        self.lockout_duration = timedelta(minutes=30)
        self.token_blacklist = set()
        self.session_timeout = timedelta(hours=12)
        self._services = {}
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize required services using lazy loading."""
        if not self._initialized:
            # Lazy load dependencies to avoid circular imports
            from .token import token_service
            from .rbac import rbac_system
            from ..security import security_manager
            
            self._services.update({
                'token': token_service,
                'rbac': rbac_system,
                'security': security_manager
            })
            self._initialized = True

    async def validate_login_attempt(self, user: Dict[str, Any], password: str) -> bool:
        """Validate login credentials and attempt count."""
        if not self._initialized:
            await self.initialize()
            
        if not user.get("isActive", False):
            return False
            
        if user.get("loginAttempts", 0) >= self.max_login_attempts:
            if self._is_account_locked(user):
                return False
                
        return await self._services['security'].verify_password(
            password, 
            user["passwordHash"]
        )

    def _is_account_locked(self, user: Dict[str, Any]) -> bool:
        """Check if account is currently locked."""
        locked_until = user.get("lockedUntil")
        if not locked_until:
            return False
        return locked_until > datetime.utcnow()

    def get_lock_expiry(self) -> datetime:
        """Get account lock expiry timestamp."""
        return datetime.utcnow() + self.lockout_duration

class SessionBase:
    """Base class for session management."""
    
    def __init__(self):
        self.max_sessions = 5
        self.session_timeout = timedelta(hours=12)

    def create_session_data(
        self,
        user_id: str,
        user_agent: str,
        ip_address: str
    ) -> Dict[str, Any]:
        """Create new session record data."""
        return {
            "userId": user_id,
            "userAgent": user_agent,
            "ipAddress": ip_address,
            "active": True,
            "createdAt": datetime.utcnow(),
            "expiresAt": datetime.utcnow() + self.session_timeout
        }

    def is_session_expired(self, session: Dict[str, Any]) -> bool:
        """Check if session has expired."""
        return datetime.utcnow() >= session["expiresAt"]

    def format_session_response(self, session: Dict[str, Any]) -> Dict[str, Any]:
        """Format session data for response."""
        return {
            "id": str(session["_id"]),
            "createdAt": session["createdAt"],
            "expiresAt": session["expiresAt"],
            "userAgent": session["userAgent"]
        }