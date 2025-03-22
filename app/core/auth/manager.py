#backend/app/core/auth/manager.py
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple
import logging
import jwt
import redis
from fastapi import HTTPException, status

from ...database import get_database
from ..exceptions import AuthenticationError, SecurityError
from ..security.base import SecurityBase
from .base import AuthenticationBase, SessionBase
from .token import TokenService
from .rbac import RoleBasedAccessControl
from ...config import get_settings
from ...core.service import BaseService
from ..utils.security_utils import verify_password

logger = logging.getLogger(__name__)
settings = get_settings()

class AuthenticationManager(BaseService, AuthenticationBase, SessionBase):
    """Manages all authentication-related operations."""
    
    def __init__(self):
        """Initialize authentication manager with required services."""
        BaseService.__init__(self)
        AuthenticationBase.__init__(self)
        SessionBase.__init__(self)
        
        self._initialized = False
        self.security = SecurityManager()
        self.token_service = None
        self.rbac = None
        self.redis = None
        
        # Session management settings
        self.max_sessions = 5
        self.session_timeout = timedelta(hours=12)
        self.token_blacklist = set()
        
        # Authentication settings
        self.max_login_attempts = 5
        self.lockout_duration = timedelta(minutes=30)
        self.password_history_limit = 5
        
        logger.info("Authentication manager initialized")

    async def initialize(self) -> None:
        """Initialize authentication manager with required services."""
        if not self._initialized:
            await super().initialize()
            
            # Initialize required services
            self.token_service = TokenService()
            self.rbac = RoleBasedAccessControl()
            
            # Initialize Redis connection
            self.redis = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                password=settings.REDIS_PASSWORD,
                decode_responses=True
            )
            
            self._initialized = True
            logger.info("Authentication manager services initialized")

    async def authenticate_user(
        self,
        email: str,
        password: str,
        user_agent: str,
        ip_address: str
    ) -> Dict[str, Any]:
        """Authenticate user and generate access tokens."""
        if not self._initialized:
            await self.initialize()

        try:
            # Get user record
            user = await self.db.users.find_one({"email": email})
            if not user:
                raise AuthenticationError("Invalid credentials")
                
            # Check account status
            if not user["isActive"]:
                raise AuthenticationError("Account is inactive")
                
            # Check account lockout
            if await self._is_account_locked(str(user["_id"])):
                raise AuthenticationError("Account is temporarily locked")
            
            # Verify password
            if not await self.security.verify_password(
                password,
                user["passwordHash"]
            ):
                await self._handle_failed_login(str(user["_id"]))
                raise AuthenticationError("Invalid credentials")
            
            # Generate tokens
            tokens = await self._generate_auth_tokens(user)
            
            # Create session record
            await self._create_session(
                user_id=str(user["_id"]),
                user_agent=user_agent,
                ip_address=ip_address,
                refresh_token=tokens["refresh_token"]
            )
            
            # Update login status
            await self._update_login_status(user["_id"])
            
            # Log successful authentication
            await self._log_authentication(
                user_id=str(user["_id"]),
                success=True,
                ip_address=ip_address,
                user_agent=user_agent
            )
            
            return {
                **tokens,
                "user": self._format_user_response(user)
            }
            
        except AuthenticationError:
            raise
        except Exception as e:
            logger.error(f"Authentication error: {str(e)}")
            raise AuthenticationError("Authentication failed")

    async def verify_token(self, token: str) -> Dict[str, Any]:
        """Verify and decode authentication token."""
        try:
            # Check token blacklist
            if token in self.token_blacklist:
                raise AuthenticationError("Token has been revoked")
            
            # Verify token
            payload = await self.token_service.verify_token(token)
            
            # Get user permissions
            permissions = await self.rbac.get_user_permissions(payload["sub"])
            payload["permissions"] = permissions
            
            return payload
            
        except jwt.ExpiredSignatureError:
            raise AuthenticationError("Token has expired")
        except jwt.InvalidTokenError:
            raise AuthenticationError("Invalid token")
        except Exception as e:
            logger.error(f"Token verification error: {str(e)}")
            raise AuthenticationError("Token verification failed")

    async def change_password(
        self,
        user_id: str,
        current_password: str,
        new_password: str
    ) -> None:
        """Change user's password with history tracking."""
        try:
            db = await get_database()
            
            # Get user record
            user = await db.users.find_one({"_id": user_id})
            if not user:
                raise SecurityError("User not found")
            
            # Verify current password
            if not await self.security.verify_password(
                current_password,
                user["passwordHash"]
            ):
                raise SecurityError("Current password is incorrect")
            
            # Validate new password
            if not self.security.validate_password(new_password):
                raise SecurityError("New password does not meet requirements")
            
            # Check password history
            if await self._is_password_reused(user_id, new_password):
                raise SecurityError("Password has been used recently")
            
            # Hash new password
            password_hash = await self.security.hash_password(new_password)
            
            # Update password with history
            await db.users.update_one(
                {"_id": user_id},
                {
                    "$set": {
                        "passwordHash": password_hash,
                        "passwordUpdatedAt": datetime.utcnow()
                    },
                    "$push": {
                        "passwordHistory": {
                            "$each": [{
                                "hash": user["passwordHash"],
                                "updatedAt": datetime.utcnow()
                            }],
                            "$slice": -self.password_history_limit
                        }
                    }
                }
            )
            
            # Invalidate existing sessions
            await self._invalidate_user_sessions(user_id)
            
        except SecurityError:
            raise
        except Exception as e:
            logger.error(f"Password change error: {str(e)}")
            raise SecurityError("Failed to change password")

    async def invalidate_token(self, token: str) -> None:
        """Invalidate authentication token."""
        try:
            # Add to blacklist
            self.token_blacklist.add(token)
            
            # Clean up expired tokens
            await self._cleanup_token_blacklist()
            
        except Exception as e:
            logger.error(f"Token invalidation error: {str(e)}")
            raise SecurityError("Failed to invalidate token")

    async def _create_session(
        self,
        user_id: str,
        user_agent: str,
        ip_address: str,
        refresh_token: str
    ) -> None:
        """Create new user session record."""
        try:
            db = await get_database()
            
            # Check active session count
            active_sessions = await db.sessions.count_documents({
                "userId": user_id,
                "active": True
            })
            
            if active_sessions >= self.max_sessions:
                # Invalidate oldest session
                oldest_session = await db.sessions.find_one(
                    {"userId": user_id, "active": True},
                    sort=[("createdAt", 1)]
                )
                await self._invalidate_session(oldest_session["_id"])
            
            # Create new session
            await db.sessions.insert_one({
                "userId": user_id,
                "userAgent": user_agent,
                "ipAddress": ip_address,
                "refreshToken": refresh_token,
                "active": True,
                "createdAt": datetime.utcnow(),
                "expiresAt": datetime.utcnow() + self.session_timeout
            })
            
        except Exception as e:
            logger.error(f"Session creation error: {str(e)}")
            raise SecurityError("Failed to create session")

    async def _generate_auth_tokens(
        self,
        user: Dict[str, Any]
    ) -> Dict[str, str]:
        """Generate authentication tokens for user."""
        return await self.token_service.create_tokens(
            user_id=str(user["_id"]),
            user_data={
                "role": user["role"],
                "permissions": user.get("permissions", []),
                "center_id": str(user.get("centerId")) if user.get("centerId") else None
            }
        )

    async def _update_login_status(self, user_id: str) -> None:
        """Update user's login status."""
        await self.db.users.update_one(
            {"_id": user_id},
            {
                "$set": {
                    "lastLogin": datetime.utcnow(),
                    "loginAttempts": 0,
                    "lockedUntil": None
                }
            }
        )

    async def _handle_failed_login(self, user_id: str) -> None:
        """Handle failed login attempt."""
        try:
            result = await self.db.users.find_one_and_update(
                {"_id": user_id},
                {
                    "$inc": {"loginAttempts": 1},
                    "$set": {"lastFailedLogin": datetime.utcnow()}
                },
                return_document=True
            )
            
            if result["loginAttempts"] >= self.max_login_attempts:
                await self._lock_account(user_id)
                
        except Exception as e:
            logger.error(f"Failed login handling error: {str(e)}")

    async def _is_account_locked(self, user_id: str) -> bool:
        """Check if account is locked due to failed attempts."""
        try:
            db = await get_database()
            user = await db.users.find_one({"_id": user_id})
            
            if not user.get("lockedUntil"):
                return False
                
            if user["lockedUntil"] > datetime.utcnow():
                return True
                
            # Reset lock if expired
            await db.users.update_one(
                {"_id": user_id},
                {
                    "$set": {
                        "lockedUntil": None,
                        "loginAttempts": 0
                    }
                }
            )
            return False
            
        except Exception as e:
            logger.error(f"Account lock check error: {str(e)}")
            return False

    async def _lock_account(self, user_id: str) -> None:
        """Lock account after max failed attempts."""
        try:
            await self.db.users.update_one(
                {"_id": user_id},
                {
                    "$set": {
                        "lockedUntil": datetime.utcnow() + self.lockout_duration
                    }
                }
            )
            
        except Exception as e:
            logger.error(f"Account locking error: {str(e)}")

    async def cleanup(self) -> None:
        """Cleanup authentication manager resources."""
        try:
            if self.redis:
                await self.redis.close()
            await super().cleanup()
            logger.info("Authentication manager cleaned up")
        except Exception as e:
            logger.error(f"Cleanup error: {str(e)}")

    async def _cleanup_token_blacklist(self) -> None:
        """Remove expired tokens from blacklist."""
        current_time = datetime.utcnow()
        self.token_blacklist = {
            token for token in self.token_blacklist
            if self.token_service.get_token_expiry(token) > current_time
        }

    def _format_user_response(self, user: Dict[str, Any]) -> Dict[str, Any]:
        """Format user data for response."""
        return {
            "id": str(user["_id"]),
            "email": user["email"],
            "fullName": user.get("fullName"),
            "role": user["role"],
            "permissions": user.get("permissions", []),
            "centerId": str(user.get("centerId")) if user.get("centerId") else None,
            "lastLogin": user.get("lastLogin")
        }

# Initialize authentication manager
auth_manager = AuthenticationManager()