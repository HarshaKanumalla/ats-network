# backend/app/services/session/session_service.py

from typing import Dict, Any, Optional, List
import logging
from datetime import datetime, timedelta
import jwt
import redis
from bson import ObjectId

from ...core.exceptions import SessionError
from ...database import get_database
from ...config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class SessionManagementService:
    """Enhanced service for managing user sessions and token lifecycle."""
    
    def __init__(self):
        """Initialize session management with security configurations."""
        self.db = None
        
        # Redis client for token blacklist and rate limiting
        self.redis = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            password=settings.REDIS_PASSWORD,
            decode_responses=True
        )
        
        # Session settings
        self.session_timeout = timedelta(hours=12)
        self.cleanup_interval = timedelta(hours=1)
        self.max_sessions_per_user = 5
        self.token_blacklist_prefix = "blacklist:"
        
        # Token settings
        self.access_token_lifetime = timedelta(minutes=30)
        self.refresh_token_lifetime = timedelta(days=7)
        self.token_algorithm = "HS256"
        
        # Rate limiting settings
        self.rate_limit_window = 900  # 15 minutes
        self.rate_limit_max_requests = {
            "login": 5,
            "api": 100,
            "refresh": 10
        }
        
        logger.info("Session management service initialized")

    async def create_session(
        self,
        user_id: str,
        user_agent: str,
        token_id: str,
        metadata: Dict[str, Any]
        ip_address: str
    ) -> Dict[str, Any]:
        """Create new user session with token generation."""
        try:
            db = await get_database()
            
            # Check active session count
            active_sessions = await db.sessions.count_documents({
                "userId": ObjectId(user_id),
                "active": True
            })
            
            if active_sessions >= self.max_sessions_per_user:
                # Invalidate oldest session
                oldest_session = await db.sessions.find_one(
                    {"userId": ObjectId(user_id), "active": True},
                    sort=[("createdAt", 1)]
                )
                await self.invalidate_session(str(oldest_session["_id"]))
            
            # Generate tokens
            access_token = self._generate_access_token(user_id)
            refresh_token = self._generate_refresh_token(user_id)
            
            # Create session record
            session_doc = {
                "userId": ObjectId(user_id),
                "tokenId": token_id,
                "metadata": metadata,
                "accessToken": access_token,
                "refreshToken": refresh_token,
                "userAgent": user_agent,
                "ipAddress": ip_address,
                "active": True,
                "createdAt": datetime.utcnow(),
                "expiresAt": datetime.utcnow() + self.session_timeout,
                "lastActivity": datetime.utcnow()
            }
            
            result = await db.sessions.insert_one(session_doc)
            session_doc["_id"] = result.inserted_id

            # Store in Redis for quick access
            await self.redis.setex(
                f"session:{session_id}",
                int(self.session_timeout.total_seconds()),
                json.dumps({
                    "userId": user_id,
                    "tokenId": token_id,
                    "expiresAt": session["expiresAt"].isoformat()
                })
            )

            return session_id
            
            logger.info(f"Created session for user: {user_id}")
            return {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "session_id": str(result.inserted_id)
            }
            
        except Exception as e:
            logger.error(f"Session creation error: {str(e)}")
            raise SessionError(f"Failed to create session: {str(e)}")

    async def refresh_tokens(
        self,
        refresh_token: str
    ) -> Dict[str, str]:
        """Refresh access token using refresh token."""
        try:
            # Verify refresh token
            payload = jwt.decode(
                refresh_token,
                settings.REFRESH_TOKEN_SECRET,
                algorithms=[self.token_algorithm]
            )
            
            # Check if token is blacklisted
            if await self._is_token_blacklisted(refresh_token):
                raise SessionError("Token has been revoked")
            
            # Rate limit check
            if not await self._check_rate_limit("refresh", payload["sub"]):
                raise SessionError("Refresh rate limit exceeded")
            
            # Generate new tokens
            new_access_token = self._generate_access_token(payload["sub"])
            new_refresh_token = self._generate_refresh_token(payload["sub"])
            
            # Update session record
            db = await get_database()
            await db.sessions.update_one(
                {"refreshToken": refresh_token},
                {
                    "$set": {
                        "accessToken": new_access_token,
                        "refreshToken": new_refresh_token,
                        "lastActivity": datetime.utcnow()
                    }
                }
            )
            
            # Blacklist old refresh token
            await self._blacklist_token(refresh_token)
            
            return {
                "access_token": new_access_token,
                "refresh_token": new_refresh_token
            }
            
        except jwt.InvalidTokenError as e:
            raise SessionError(f"Invalid refresh token: {str(e)}")
        except Exception as e:
            logger.error(f"Token refresh error: {str(e)}")
            raise SessionError("Failed to refresh tokens")


     async def validate_session(self, session_id: str) -> bool:
        """Validate session status and expiry."""
        try:
            # Check Redis first
            session_data = await self.redis.get(f"session:{session_id}")
            if not session_data:
                return False
            
            session = json.loads(session_data)
            expires_at = datetime.fromisoformat(session["expiresAt"])
            
            if datetime.utcnow() >= expires_at:
                await self.invalidate_session(session_id)
                return False
                
            return True
            
        except Exception as e:
            logger.error(f"Session validation error: {str(e)}")
            return False

    async def invalidate_session(self, session_id: str) -> None:
        """Invalidate user session and blacklist tokens."""
        try:
            db = await get_database()
            
            session = await db.sessions.find_one({"_id": ObjectId(session_id)})
            if not session:
                raise SessionError("Session not found")
            
            # Blacklist tokens
            await self._blacklist_token(session["accessToken"])
            await self._blacklist_token(session["refreshToken"])
            
            # Update session status
            await db.sessions.update_one(
                {"_id": ObjectId(session_id)},
                {
                    "$set": {
                        "active": False,
                        "invalidatedAt": datetime.utcnow()
                    }
                }
            )
            
            logger.info(f"Invalidated session: {session_id}")
            
        except Exception as e:
            logger.error(f"Session invalidation error: {str(e)}")
            raise SessionError("Failed to invalidate session")

    async def cleanup_expired_sessions(self) -> None:
        """Clean up expired sessions and tokens."""
        try:
            db = await get_database()
            current_time = datetime.utcnow()
            
            # Find expired sessions
            expired_sessions = await db.sessions.find({
                "active": True,
                "expiresAt": {"$lt": current_time}
            }).to_list(None)
            
            # Invalidate expired sessions
            for session in expired_sessions:
                await self.invalidate_session(str(session["_id"]))
            
            # Clean up token blacklist
            await self._cleanup_token_blacklist()
            
            logger.info(f"Cleaned up {len(expired_sessions)} expired sessions")
            
        except Exception as e:
            logger.error(f"Session cleanup error: {str(e)}")
            raise SessionError("Failed to cleanup sessions")

    async def _check_rate_limit(
        self,
        action: str,
        user_id: str
    ) -> bool:
        """Check rate limit for specific action."""
        try:
            key = f"rate_limit:{action}:{user_id}"
            current = await self.redis.get(key)
            
            if current and int(current) >= self.rate_limit_max_requests[action]:
                return False
            
            pipeline = self.redis.pipeline()
            pipeline.incr(key)
            pipeline.expire(key, self.rate_limit_window)
            await pipeline.execute()
            
            return True
            
        except Exception as e:
            logger.error(f"Rate limit check error: {str(e)}")
            return True  # Allow request if rate limiting fails

    def _generate_access_token(self, user_id: str) -> str:
        """Generate new access token."""
        payload = {
            "sub": user_id,
            "type": "access",
            "exp": datetime.utcnow() + self.access_token_lifetime
        }
        return jwt.encode(
            payload,
            settings.ACCESS_TOKEN_SECRET,
            algorithm=self.token_algorithm
        )

    def _generate_refresh_token(self, user_id: str) -> str:
        """Generate new refresh token."""
        payload = {
            "sub": user_id,
            "type": "refresh",
            "exp": datetime.utcnow() + self.refresh_token_lifetime
        }
        return jwt.encode(
            payload,
            settings.REFRESH_TOKEN_SECRET,
            algorithm=self.token_algorithm
        )

    async def _blacklist_token(self, token: str) -> None:
        """Add token to blacklist."""
        try:
            key = f"{self.token_blacklist_prefix}{token}"
            await self.redis.setex(
                key,
                self.refresh_token_lifetime.total_seconds(),
                "1"
            )
        except Exception as e:
            logger.error(f"Token blacklisting error: {str(e)}")

    async def _is_token_blacklisted(self, token: str) -> bool:
        """Check if token is blacklisted."""
        try:
            key = f"{self.token_blacklist_prefix}{token}"
            return bool(await self.redis.exists(key))
        except Exception as e:
            logger.error(f"Token blacklist check error: {str(e)}")
            return False

    async def _cleanup_token_blacklist(self) -> None:
        """Clean up expired tokens from blacklist."""
        try:
            pattern = f"{self.token_blacklist_prefix}*"
            keys = await self.redis.keys(pattern)
            
            if keys:
                await self.redis.delete(*keys)
                
            logger.info(f"Cleaned up {len(keys)} blacklisted tokens")
            
        except Exception as e:
            logger.error(f"Token blacklist cleanup error: {str(e)}")

# Initialize session management service
session_service = SessionManagementService()