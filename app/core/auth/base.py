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
            try:
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
                logger.info("Authentication services initialized successfully.")
            except ImportError as e:
                logger.error(f"Failed to initialize authentication services: {str(e)}")
                raise

    async def validate_login_attempt(self, user: Dict[str, Any], password: str) -> bool:
        """
        Validate login credentials and attempt count.

        Args:
            user (Dict[str, Any]): User data containing login details.
            password (str): The password to validate.

        Returns:
            bool: True if the login attempt is valid, False otherwise.
        """
        try:
            if not self._initialized:
                await self.initialize()
            
            if not user or "passwordHash" not in user:
                logger.error("Invalid user data provided for login validation.")
                return False

            if not user.get("isActive", False):
                logger.warning(f"Login attempt for inactive user ID: {user.get('id')}")
                return False

            if user.get("loginAttempts", 0) >= self.max_login_attempts:
                if self._is_account_locked(user):
                    logger.warning(f"Account locked for user ID: {user.get('id')}")
                    return False

            is_valid = await self._services['security'].verify_password(
                password, 
                user["passwordHash"]
            )
            if not is_valid:
                logger.warning(f"Invalid password for user ID: {user.get('id')}")
            return is_valid

        except Exception as e:
            logger.error(f"Error during login validation: {str(e)}")
            return False

    def _is_account_locked(self, user: Dict[str, Any]) -> bool:
        """
        Check if account is currently locked.

        Args:
            user (Dict[str, Any]): User data.

        Returns:
            bool: True if the account is locked, False otherwise.
        """
        locked_until = user.get("lockedUntil")
        if not locked_until:
            return False
        if locked_until > datetime.utcnow():
            logger.warning(f"Account is locked until {locked_until}")
            return True
        return False

    def get_lock_expiry(self) -> datetime:
        """
        Get account lock expiry timestamp.

        Returns:
            datetime: The timestamp when the lock expires.
        """
        return datetime.utcnow() + self.lockout_duration

    def blacklist_token(self, token: str) -> None:
        """
        Add a token to the blacklist.

        Args:
            token (str): The token to blacklist.
        """
        self.token_blacklist.add(token)
        logger.info(f"Token blacklisted: {token[:10]}...")

    def is_token_blacklisted(self, token: str) -> bool:
        """
        Check if a token is blacklisted.

        Args:
            token (str): The token to check.

        Returns:
            bool: True if the token is blacklisted, False otherwise.
        """
        return token in self.token_blacklist


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
        """
        Create new session record data.

        Args:
            user_id (str): The ID of the user.
            user_agent (str): The user agent string.
            ip_address (str): The IP address of the user.

        Returns:
            Dict[str, Any]: The session data.
        """
        if not user_id or not user_agent or not ip_address:
            logger.error("Invalid session data provided.")
            raise ValueError("User ID, user agent, and IP address are required.")

        session_data = {
            "userId": user_id,
            "userAgent": user_agent,
            "ipAddress": ip_address,
            "active": True,
            "createdAt": datetime.utcnow(),
            "expiresAt": datetime.utcnow() + self.session_timeout
        }
        logger.info(f"Session created for user ID: {user_id}, IP: {ip_address}")
        return session_data

    def is_session_expired(self, session: Dict[str, Any]) -> bool:
        """
        Check if session has expired.

        Args:
            session (Dict[str, Any]): The session data.

        Returns:
            bool: True if the session has expired, False otherwise.
        """
        if "expiresAt" not in session:
            logger.error("Session data is missing 'expiresAt' field.")
            return True
        return datetime.utcnow() >= session["expiresAt"]

    def format_session_response(self, session: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format session data for response.

        Args:
            session (Dict[str, Any]): The session data.

        Returns:
            Dict[str, Any]: The formatted session data.
        """
        if "_id" not in session:
            logger.error("Session data is missing '_id' field.")
            raise ValueError("Invalid session data: '_id' field is required.")

        return {
            "id": str(session["_id"]),
            "createdAt": session["createdAt"],
            "expiresAt": session["expiresAt"],
            "userAgent": session["userAgent"]
        }

    def enforce_max_sessions(self, user_sessions: List[Dict[str, Any]]) -> None:
        """
        Enforce maximum session limit by deactivating the oldest sessions.

        Args:
            user_sessions (List[Dict[str, Any]]): List of user sessions.
        """
        if len(user_sessions) > self.max_sessions:
            user_sessions.sort(key=lambda s: s["createdAt"])
            for session in user_sessions[:-self.max_sessions]:
                session["active"] = False
                logger.info(f"Deactivated session ID: {session['_id']} due to max session limit.")